"""Explicit ACF path discovery, safe YAML/frontmatter parsing and schemas."""
from datetime import date, datetime
import json
from pathlib import Path

import yaml


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    seen = set()
    for key, _ in node.value:
        if key.tag not in ("tag:yaml.org,2002:str", "tag:yaml.org,2002:merge"):
            raise yaml.constructor.ConstructorError(
                None, None, "ACF mapping keys must be strings", key.start_mark)
        if key.value in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate YAML key: {key.value}", key.start_mark)
        seen.add(key.value)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def normalize_dates(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: normalize_dates(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_dates(v) for v in value]
    return value


def read_yaml(path):
    return normalize_dates(yaml.load(Path(path).read_text(), Loader=UniqueLoader))


def read_method(path):
    lines = Path(path).read_text().splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("method must start with YAML frontmatter delimiter ---")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("method frontmatter is missing closing ---") from None
    data = normalize_dates(yaml.load("\n".join(lines[1:end]), Loader=UniqueLoader))
    return data, "\n".join(lines[end + 1:])


def discover_docs(root, templates=False):
    """Only contract locations, never caches or nested context roots."""
    root = Path(root)
    docs = []
    if (root / "context.config.yaml").is_file():
        docs.append((root / "context.config.yaml", "config"))
    for domain in sorted((root / "domains").glob("*")):
        if not domain.is_dir() or (domain.name.startswith("_") and not templates):
            continue
        for filename, kind in (("domain.yaml", "domain"), ("entities.yaml", "entity"),
                               ("metrics.yaml", "legacy"), ("metrics.yml", "legacy")):
            if (domain / filename).is_file():
                docs.append((domain / filename, kind))
        docs.extend((path, "legacy") for path in sorted(domain.iterdir())
                    if path.is_file() and path.name.casefold() == "metrics.lookml")
        for path in sorted((domain / "metrics").glob("*.yaml")):
            if path.name.startswith("_") and path.name != "_shared.yaml" and not templates:
                continue
            docs.append((path, "shared" if path.name == "_shared.yaml" else "metric"))
    for pattern, kind in (("entities/*.yaml", "entity"), ("methods/*.md", "method"),
                          ("evals/seeds/*.seed.yaml", "evalseed")):
        docs.extend((p, kind) for p in sorted(root.glob(pattern))
                    if templates or not p.name.startswith("_"))
    return docs


class Schemas:
    def __init__(self, directory):
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
        self.raw = {p.name.removesuffix(".schema.json"): json.loads(p.read_text())
                    for p in Path(directory).glob("*.schema.json")}
        if not self.raw:
            raise ValueError(f"no schemas found at {directory}")
        registry = Registry().with_resources(
            (s["$id"], Resource.from_contents(s)) for s in self.raw.values())
        self.validators = {k: Draft202012Validator(v, registry=registry,
                                                   format_checker=FormatChecker())
                           for k, v in self.raw.items()}

    def errors(self, kind, data):
        return sorted(self.validators[kind].iter_errors(data),
                      key=lambda e: "/".join(map(str, e.path)))


def load_context(root, schemas=None, manifests=None, *, branch_test=None, authority=None):
    """Return a Registry with located diagnostics. Never mutates authored files."""
    from .registry import Registry
    from .fragments import expand_metric, FragmentError
    import os
    if branch_test is None:
        branch_test = os.environ.get("ACF_BRANCH_TEST") == "1"
    root = Path(root).resolve()
    schema_dir = Path(schemas) if schemas else root / "schemas"
    if not schema_dir.is_dir() and schemas is None:
        schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    checker = Schemas(schema_dir)
    result = Registry(root, manifests or {})
    parsed = []
    fragments, usage = {}, {}
    for path, kind in discover_docs(root):
        relative = path.relative_to(root).as_posix()
        if not path.resolve().is_relative_to(root):
            result.error("path.escape", relative, "", "source escapes context root")
            continue
        if kind == "legacy":
            instruction = ("run scripts/split_metrics.py" if path.suffix in (".yaml", ".yml")
                           else "author reviewed per-metric YAML; LookML conversion is not supported")
            result.error("layout.legacy", relative, "", f"{path.name} is unsupported in ACF 0.3; {instruction}")
            continue
        try:
            data, body = read_method(path) if kind == "method" else (read_yaml(path), "")
        except (OSError, ValueError, yaml.YAMLError, RecursionError) as exc:
            result.error("parse.invalid", relative, "", str(exc))
            continue
        if not isinstance(data, dict):
            result.error("parse.object", relative, "", "expected an object")
            continue
        if kind in ("shared", "config"):
            errors = checker.errors(kind, data)
            for err in errors:
                result.error("schema.invalid", relative, "/".join(map(str, err.path)), err.message)
            if errors:
                continue
            if kind == "shared":
                fragments[path.parent] = data
            else:
                result.config = data
        parsed.append((path, relative, kind, data, body))
    if not result.config:
        result.error("config.required", "context.config.yaml", "version",
                     "a valid ACF 0.3 config is required; older repos must migrate")
    for path, relative, kind, data, body in parsed:
        if kind in ("shared", "config"):
            continue
        if kind == "metric":
            origins = result.fragment_origins.setdefault(relative, [])
            try:
                data = expand_metric(data, fragments.get(path.parent, {}), usage, relative, origins)
            except FragmentError as exc:
                result.error("fragment.invalid", relative, exc.reference_field, str(exc))
                continue
            except (ValueError, TypeError, KeyError) as exc:
                result.error("fragment.invalid", relative, "", str(exc))
                continue
        errors = checker.errors(kind, data)
        for err in errors:
            result.error("schema.invalid", relative, "/".join(map(str, err.path)), err.message)
        if not errors:
            result.add(kind, relative, data, body)
    for folder, doc in fragments.items():
        relative = (folder / "_shared.yaml").relative_to(root).as_posix()
        for namespace, entries in doc.items():
            for name in entries:
                count = len(usage.get((str(folder.relative_to(root)), namespace, name), set()))
                if count < 2:
                    result.warn("fragment.low_use", relative, f"{namespace}/{name}",
                                f"fragment has {count} referring metrics; inline fragments used fewer than twice")
    result.build()
    from .governance import apply_governance
    from .status import resolve_status
    apply_governance(result, branch_test=branch_test, authority=authority)
    resolve_status(result.nodes)
    return result
