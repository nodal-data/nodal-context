#!/usr/bin/env python3
"""Validate Analytics Context Format (ACF) docs against the JSON Schemas.

Dual-mode (option A) — one script for both places it runs:

  • In a *context* repo (the analyst's analytics-context repo) the ACF docs live at
    the repo root (./context.config.yaml, ./domains/**, ./entities/**, ./evals/**).
    Run with no args; the script validates that root strictly.

  • In *this tool* repo there are no root-level context docs — the shipped ACF lives
    under examples/<company>/ and template/. With no args here, the script strictly
    validates each examples/*/ (they are real worked examples and must pass) and does
    a lenient *structural* check on template/ (it is full of `<placeholder>` values
    that intentionally don't satisfy the schemas — we check field parallelism, not
    values). This is the regression test CLAUDE.md asks for: "does examples/ still
    validate against schemas/, and does template/ match?"

  python .ci/validate.py                # auto-discover (see above)
  python .ci/validate.py path/to/root   # validate one or more explicit roots, strict
  python .ci/validate.py --schemas schemas

Exit 0 = valid (drafts are warned, not failed); 1 = schema/structure errors;
2 = setup error (schemas dir or deps missing).
"""
import argparse
import glob
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# filename/pattern -> ACF kind -> schema file. lineage is only $ref'd, never paired.
KIND_BY_NAME = {
    "context.config.yaml": "config",
    "domain.yaml": "domain",
    "metrics.yaml": "metric",
    "entities.yaml": "entity",
}
SCHEMA_FILE = {
    "config": "config.schema.json",
    "domain": "domain.schema.json",
    "metric": "metric.schema.json",
    "entity": "entity.schema.json",
    "evalseed": "evalseed.schema.json",
}


def _die(msg, code=2):
    print(f"validate: ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _resolve_schemas_dir(arg):
    for cand in (arg, "schemas", str(SCRIPT_DIR.parent / "schemas")):
        if cand and Path(cand).is_dir():
            return Path(cand)
    _die("could not find a schemas/ directory (pass --schemas)")


def _kind_for(path: Path):
    """Map a yaml file to its ACF kind, or None if it isn't an ACF doc we validate."""
    name = path.name
    if name in KIND_BY_NAME:
        return KIND_BY_NAME[name]
    if name.endswith(".seed.yaml"):
        return "evalseed"
    # entity files may live under an entities/ directory with arbitrary names
    if path.suffix in (".yaml", ".yml") and "entities" in path.parts:
        return "entity"
    return None


def discover_docs(root: Path):
    """[(path, kind)] for every ACF doc under root."""
    out = []
    for p in sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml")):
        kind = _kind_for(p)
        if kind:
            out.append((p, kind))
    return out


def _load_yaml(path, yaml):
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        return e  # caller reports


# ----- strict (schema) validation --------------------------------------------

def validate_strict(docs, schemas, validator_cls, registry, yaml):
    """Returns (errors, draft_count)."""
    errors, drafts = [], 0
    for path, kind in docs:
        doc = _load_yaml(path, yaml)
        if not isinstance(doc, dict) and not isinstance(doc, list):
            errors.append(f"{path}: not valid YAML ({doc})")
            continue
        if isinstance(doc, dict):
            drafts += int(doc.get("status") == "draft")
            if kind in ("metric", "entity"):
                items = doc.get("metrics" if kind == "metric" else "entities", [])
                if isinstance(items, list):
                    drafts += sum(isinstance(item, dict) and item.get("status") == "draft"
                                  for item in items)
        v = validator_cls(schemas[kind], registry=registry)
        for err in sorted(v.iter_errors(doc), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "(root)"
            errors.append(f"{path} [{kind}] at {loc}: {err.message}")
    return errors, drafts


# ----- deterministic expression semantics ------------------------------------

class MeasureParser:
    """Small recursive-descent grammar; never evaluates input or accepts SQL."""

    TOKEN = re.compile(
        r"\s*(?:(metric\s*\(\s*[A-Za-z_][A-Za-z0-9_.-]*\s*\))|"
        r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)|"
        r"((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)|([()+*/-]))")
    AGGREGATES = {"SUM", "COUNT", "AVG", "MIN", "MAX"}

    def __init__(self, measure):
        if not isinstance(measure, str) or not measure.strip():
            raise ValueError("measure must be a nonempty expression")
        self.tokens, self.columns, self.references = [], set(), set()
        self.has_aggregate = False
        pos = 0
        measure = measure.strip()
        while pos < len(measure):
            match = self.TOKEN.match(measure, pos)
            if not match:
                raise ValueError(f"unsupported measure syntax near {measure[pos:pos + 30]!r}")
            self.tokens.append(next((i, v) for i, v in enumerate(match.groups()) if v is not None))
            pos = match.end()
        self.index = 0

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else (None, "")

    def take(self, value=None):
        token = self.peek()
        if not token[1] or (value is not None and token[1] != value):
            raise ValueError(f"expected {value or 'operand'}, got {token[1] or 'end of measure'}")
        self.index += 1
        return token

    def parse(self):
        self.expression()
        if self.peek()[1]:
            raise ValueError(f"unexpected token {self.peek()[1]!r}")
        return self

    def expression(self):
        self.term()
        while self.peek()[1] in ("+", "-"):
            self.take()
            self.term()

    def term(self):
        self.atom()
        while self.peek()[1] in ("*", "/"):
            self.take()
            self.atom()

    def atom(self):
        kind, value = self.take()
        if value in ("+", "-"):
            self.atom()
        elif value == "(":
            self.expression()
            self.take(")")
        elif kind == 0:
            self.references.add(value[value.index("(") + 1:-1].strip())
        elif kind == 2:
            return
        elif kind == 1 and value.upper() in self.AGGREGATES:
            self.has_aggregate = True
            self.take("(")
            distinct = self.peek()[1].upper() == "DISTINCT"
            if distinct:
                self.take()
            arg_kind, arg = self.take()
            if arg == "*" and value.upper() == "COUNT" and not distinct:
                pass
            elif arg_kind == 1:
                self.columns.add(arg)
            else:
                raise ValueError("aggregate requires a column (or COUNT(*))")
            self.take(")")
        else:
            raise ValueError(f"unsupported operand {value!r}; use aggregates or metric(name)")


def filter_fields(filters):
    for item in filters or []:
        if "field" in item:
            yield item["field"]
        else:
            yield from filter_fields(item.get("any_of", item.get("all_of", [])))


def expression_checks(docs, yaml, manifests=None):
    """Validate file-local reference graphs and columns; return errors, warnings.

    Manifests are keyed by lineage source, matching drift.py's --manifest option.
    Missing manifests leave column membership unchecked, never guessed.
    Schema-invalid metric files are excluded by the caller.
    """
    errors, warnings = [], []
    manifests = manifests or {}
    model_columns = {}
    for source, manifest in manifests.items():
        index = {}
        for node in list(manifest.get("nodes", {}).values()) + list(manifest.get("sources", {}).values()):
            if node.get("resource_type") not in ("model", "seed", "snapshot", "source"):
                continue
            columns = {c.lower() for c in node.get("columns", {})}
            for key in (node.get("name"), node.get("unique_id")):
                if key:
                    index.setdefault(key, []).append(columns)
        model_columns[source] = index

    for path, kind in docs:
        if kind != "metric":
            continue
        doc = _load_yaml(path, yaml)
        metrics = {}
        for metric in doc.get("metrics", []):
            name = metric["name"]
            if name in metrics:
                errors.append(f"{path}: duplicate metric name {name!r}")
            metrics[name] = metric
        parsed, dependencies, own_columns = {}, {}, {}
        for name, metric in metrics.items():
            expr = metric.get("expression")
            if expr is None:
                continue
            label = f"{path}: metric {name!r}"
            try:
                measure = MeasureParser(expr["measure"]).parse()
                refs = set(measure.references)
                columns = set(measure.columns)
                for group in expr.get("entity_filters", []):
                    columns.add(group["entity"])
                    for condition in group["having"]:
                        having = MeasureParser(condition["measure"]).parse()
                        columns.update(having.columns)
                        refs.update(having.references)
                parsed[name] = measure
                dependencies[name] = refs
                own_columns[name] = columns
            except (ValueError, RecursionError) as exc:
                errors.append(f"{label}: invalid measure: {exc}")
                continue
            # COUNT(*) and constant-only measures also need a row source. Only
            # reference-only arithmetic may omit its own lineage.
            if (measure.has_aggregate or not measure.references) and not any(
                    p.get("models") for p in metric.get("lineage", [])):
                errors.append(f"{label}: column/row measures require lineage models")
            for ref in sorted(refs):
                target = metrics.get(ref)
                if target is None:
                    errors.append(f"{label}: metric({ref}) is not defined in this metrics.yaml")
                elif "expression" not in target:
                    errors.append(f"{label}: metric({ref}) has no expression")
                else:
                    dims = set(expr.get("allowed_dimensions", []))
                    target_dims = target["expression"].get("allowed_dimensions")
                    if dims and (target_dims is None or not dims.issubset(target_dims)):
                        errors.append(f"{label}: allowed_dimensions must be a subset of metric({ref})'s enumerated dimensions")
            if refs or expr.get("entity_filters") or any(
                    "any_of" in f or "all_of" in f for f in expr.get("mandatory_filters", [])):
                warnings.append(f"{label}: uses ACF 0.2 expressions; consumers without group/entity/reference support degrade this definition")

        resolved, visiting = {}, []

        def lineage(name):
            if name in resolved:
                return resolved[name]
            if name in visiting:
                errors.append(f"{path}: cyclic metric references: {' -> '.join(visiting + [name])}")
                return set()
            visiting.append(name)
            metric = metrics.get(name, {})
            result = {(p["source"], m) for p in metric.get("lineage", []) for m in p.get("models", [])}
            for ref in sorted(dependencies.get(name, [])):
                result |= lineage(ref)
            visiting.pop()
            resolved[name] = result
            return result

        def check_columns(name, fields, pointers):
            if not fields or not pointers:
                return
            known, complete = {}, True
            for source, model in sorted(pointers):
                if source not in model_columns:
                    complete = False
                    continue
                candidates = model_columns[source].get(model, [])
                if len(candidates) != 1:
                    errors.append(f"{path}: metric {name!r}: lineage model {source}/{model} is missing or ambiguous in manifest")
                    complete = False
                    continue
                known[(source, model)] = candidates[0]
            for field in sorted(fields):
                qualifier, sep, column = field.rpartition(".")
                matches = [cols for (_, model), cols in known.items()
                           if not sep or model == qualifier or model.split(".")[-1] == qualifier]
                if complete and not any((column if sep else field).lower() in cols for cols in matches):
                    errors.append(f"{path}: metric {name!r}: column {field!r} is absent from lineage models")

        for name in parsed:
            try:
                pointers = lineage(name)
            except RecursionError:
                errors.append(f"{path}: metric reference graph exceeds supported nesting depth")
                continue
            metric = metrics[name]
            expr = metric["expression"]
            own = {(p["source"], m) for p in metric.get("lineage", []) for m in p.get("models", [])}
            check_columns(name, own_columns[name], own or pointers)
            fields = set(filter_fields(expr.get("mandatory_filters")))
            check_columns(name, fields | set(expr.get("allowed_dimensions", [])), pointers)
            # Overlay filters must work on every referenced branch, including
            # transitive references; a union alone can mask an invalid overlay.
            seen = set()
            def check_overlay(ref):
                if ref in seen:
                    return
                seen.add(ref)
                check_columns(name, fields, resolved.get(ref, set()))
                for child in dependencies.get(ref, []):
                    check_overlay(child)
            for ref in dependencies.get(name, []):
                check_overlay(ref)
    return errors, warnings


# ----- lineage repo sanity (warn, never fail) --------------------------------

def lineage_repo_warnings(docs, yaml):
    """Warn when a lineage source's `repo` is a local filesystem path. The drift
    workflow clones `repo` in CI, so a local path means drift can never run for
    that source. Extraction-time clone paths are session state — the durable value
    is the git remote (github.com/org/repo), or omit `repo:` if none exists yet."""
    warns = []
    for path, kind in docs:
        if kind != "config":
            continue
        doc = _load_yaml(path, yaml)
        if not isinstance(doc, dict):
            continue
        for src in doc.get("lineage_sources") or []:
            if not isinstance(src, dict):
                continue
            repo = str(src.get("repo") or "")
            if repo.startswith(("local:", "file:", "/", "~", ".")):
                warns.append(
                    f"{path}: lineage source '{src.get('id')}' has a local repo path "
                    f"('{repo}') — CI cannot clone it, so drift monitoring is off for "
                    "this source. Set `repo:` to the git remote (e.g. "
                    "github.com/org/repo), or omit it until one exists.")
    return warns


# ----- entity placement (warn, never fail) ------------------------------------

def entity_placement_warnings(docs, yaml, root):
    """Warn when entity definitions exist only per-domain. Both locations are
    valid ACF, but consumers (compile_skill, the Nodal platform index) surface
    top-level entities/ as the primary entity listing, so subject entities filed
    only under domains/*/entities.yaml are slower to discover. Two signals:
      - domains/*/entities.yaml defines entities while entities/ has no real
        (non-underscore) file → suggest promoting subject entities;
      - the same entity name in ≥2 domains → cross-domain by definition."""
    root = Path(root).resolve()
    has_top_level = False
    per_domain = {}  # domain -> (rel path, [entity names])
    for path, kind in docs:
        if kind != "entity":
            continue
        rel = path.resolve().relative_to(root)
        if rel.parts[0] == "entities":
            if not path.name.startswith("_"):
                has_top_level = True
        elif (rel.parts[0] == "domains" and len(rel.parts) >= 3
              and not rel.parts[1].startswith("_")):
            doc = _load_yaml(path, yaml)
            names = [e["name"] for e in (doc.get("entities") or [])
                     if isinstance(e, dict) and e.get("name")] \
                if isinstance(doc, dict) else []
            per_domain[rel.parts[1]] = (rel, names)

    warns = []
    total = sum(len(names) for _, names in per_domain.values())
    if total and not has_top_level:
        files = ", ".join(str(rel) for rel, _ in per_domain.values())
        warns.append(
            f"{total} entity(ies) defined only per-domain ({files}) and entities/ "
            "has no real file — subject entities (business nouns: customer, "
            "channel, geography, …) belong in entities/<group>.yaml even in a "
            "single-domain repo; consumers index entities/ first, so retrieval "
            "performs better there. Keep only single-fact-table status/type "
            "values per-domain. See the placement rule in SPEC.md.")
    domains_by_name = {}
    for domain, (_rel, names) in per_domain.items():
        for n in names:
            domains_by_name.setdefault(n, []).append(domain)
    for n, ds in sorted(domains_by_name.items()):
        if len(ds) >= 2:
            warns.append(
                f"entity '{n}' is defined in {len(ds)} domains "
                f"({', '.join(sorted(ds))}) — cross-domain by definition; "
                "promote it to entities/<group>.yaml.")
    return warns


def canonical_name_warnings(root):
    """Warn on near-miss filenames. Consumers match canonical names exactly
    (KIND_BY_NAME above, the platform index, compile_skill), so a
    domains/<d>/domain.yml is silently invisible — not validated, not indexed."""
    warns = []
    for p in sorted(Path(root).glob("domains/*/*.yml")):
        if p.parent.name.startswith("_"):
            continue
        if p.name in ("domain.yml", "metrics.yml", "entities.yml"):
            warns.append(
                f"{p}: consumers match '{p.stem}.yaml' exactly — this .yml "
                "variant is not validated or indexed; rename to .yaml.")
    return warns


# ----- IR coverage (warn, never fail) -----------------------------------------

def ir_coverage_report(docs, yaml):
    """Cross-check each seed's `ir.metric` against the root's metrics.yaml docs.
    Dangling references warn (never fail). The summary line is the computable form
    of "a question is covered iff an IR-complete definition exists": confirmed
    seeds whose ir.metric resolves to an expression-bearing metric, over all
    confirmed seeds. Returns (warnings, summary_or_None)."""
    metrics_by_domain = {}  # domain -> {metric name: has expression}
    for path, kind in docs:
        if kind != "metric":
            continue
        doc = _load_yaml(path, yaml)
        if not isinstance(doc, dict):
            continue
        domain = path.parent.name
        for m in doc.get("metrics") or []:
            if isinstance(m, dict) and m.get("name"):
                metrics_by_domain.setdefault(domain, {})[m["name"]] = \
                    bool(m.get("expression"))
    warns, covered, confirmed = [], 0, 0
    for path, kind in docs:
        if kind != "evalseed":
            continue
        doc = _load_yaml(path, yaml)
        if not isinstance(doc, dict):
            continue
        if doc.get("status") == "confirmed":
            confirmed += 1
        ir = doc.get("ir")
        if not isinstance(ir, dict):
            continue
        domain, metric = doc.get("domain", ""), ir.get("metric")
        known = metrics_by_domain.get(domain, {})
        if metric not in known:
            warns.append(f"{path}: ir.metric '{metric}' is not defined in "
                         f"domains/{domain}/metrics.yaml — dangling IR reference")
        elif doc.get("status") == "confirmed" and known[metric]:
            covered += 1
    summary = (f"IR coverage: {covered}/{confirmed} confirmed seed(s) resolve to "
               "an expression-bearing metric") if confirmed else None
    return warns, summary


# ----- lenient (structural) check for template/ ------------------------------

def check_structure(docs, raw_schemas, yaml):
    """Field-parallelism check: top-level keys ⊆ schema properties, and the schema's
    required keys ⊆ doc keys. Ignores placeholder *values*. Object schemas only."""
    errors = []
    for path, kind in docs:
        doc = _load_yaml(path, yaml)
        if isinstance(doc, Exception):
            errors.append(f"{path}: not valid YAML ({doc})")
            continue
        if not isinstance(doc, dict):
            continue  # list-shaped template (e.g. multiple stubs) — skip structural
        schema = raw_schemas[kind]
        props = schema.get("properties")
        if schema.get("type") != "object" or not isinstance(props, dict):
            continue  # non-object schema: nothing to compare structurally
        allowed = set(props)
        if not schema.get("additionalProperties", True):
            stray = set(doc) - allowed
            if stray:
                errors.append(f"{path} [{kind}]: unknown field(s) not in schema: "
                              f"{', '.join(sorted(stray))}")
        missing = set(schema.get("required", [])) - set(doc)
        if missing:
            errors.append(f"{path} [{kind}]: missing required field(s): "
                          f"{', '.join(sorted(missing))}")
    return errors


def discover_roots():
    """Auto-discover what to validate based on which repo we're in."""
    if Path("context.config.yaml").exists() or Path("domains").is_dir():
        return [Path(".")], None                       # a context repo: strict root
    strict = [Path(p) for p in sorted(glob.glob("examples/*")) if Path(p).is_dir()]
    structural = Path("template") if Path("template").is_dir() else None
    return strict, structural


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="*", help="context root(s) to validate strictly")
    ap.add_argument("--manifest", action="append", default=[], metavar="SOURCE_ID=PATH",
                    help="optional local dbt manifest for column checks; repeatable")
    ap.add_argument("--schemas", help="path to schemas/ (default: ./schemas or beside .ci/)")
    args = ap.parse_args(argv)

    try:
        import yaml, jsonschema
        from referencing import Registry, Resource
    except ImportError as e:
        _die(f"missing dependency ({e}); run: pip install jsonschema pyyaml")

    manifests = {}
    for pair in args.manifest:
        source, sep, filename = pair.partition("=")
        if not sep or not source or not filename:
            _die(f"--manifest expects SOURCE_ID=PATH, got {pair!r}")
        try:
            manifest = json.loads(Path(filename).read_text())
            if not isinstance(manifest, dict) or any(
                    not isinstance(manifest.get(k, {}), dict) for k in ("nodes", "sources")):
                raise ValueError("manifest must contain nodes/sources objects")
            manifests[source] = manifest
        except (OSError, ValueError) as exc:
            _die(f"cannot load manifest {filename!r}: {exc}")

    schemas_dir = _resolve_schemas_dir(args.schemas)
    raw = {}  # kind -> schema dict
    resources = []
    for sfile in glob.glob(str(schemas_dir / "*.json")):
        contents = json.load(open(sfile))
        sid = contents.get("$id")
        if sid:
            resources.append((sid, Resource.from_contents(contents)))
    registry = Registry().with_resources(resources)
    for kind, fname in SCHEMA_FILE.items():
        fpath = schemas_dir / fname
        if not fpath.exists():
            _die(f"schema {fname} not found in {schemas_dir}")
        raw[kind] = json.load(open(fpath))
    validator_cls = jsonschema.Draft202012Validator

    if args.roots:
        strict_roots, structural_root = [Path(r) for r in args.roots], None
    else:
        strict_roots, structural_root = discover_roots()

    if not strict_roots and not structural_root:
        print("validate: no ACF docs found to validate")
        return 0

    all_errors, all_warnings, total_docs, total_drafts = [], [], 0, 0

    for root in strict_roots:
        docs = discover_docs(root)
        total_docs += len(docs)
        errs, drafts = validate_strict(docs, raw, validator_cls, registry, yaml)
        total_drafts += drafts
        valid_metric_docs = [(p, k) for p, k in docs if k == "metric" and
                             validator_cls(raw[k], registry=registry).is_valid(_load_yaml(p, yaml))]
        semantic_errors, semantic_warnings = expression_checks(valid_metric_docs, yaml, manifests)
        errs += semantic_errors
        all_warnings += semantic_warnings
        all_errors += errs
        all_warnings += lineage_repo_warnings(docs, yaml)
        all_warnings += entity_placement_warnings(docs, yaml, root)
        all_warnings += canonical_name_warnings(root)
        ir_warns, ir_summary = ir_coverage_report(docs, yaml)
        all_warnings += ir_warns
        print(f"validate: {root}/ — {len(docs)} doc(s), "
              f"{len(errs)} error(s), {drafts} draft(s)"
              + (f" — {ir_summary}" if ir_summary else ""))

    if structural_root:
        docs = discover_docs(structural_root)
        total_docs += len(docs)
        errs = check_structure(docs, raw, yaml)
        all_errors += errs
        all_warnings += lineage_repo_warnings(docs, yaml)
        print(f"validate: {structural_root}/ — {len(docs)} doc(s) (structural), "
              f"{len(errs)} error(s)")

    if all_warnings:
        print(f"\nvalidate: WARNING — {len(all_warnings)} problem(s) "
              "(not a failure):")
        for w in all_warnings:
            print(f"  - {w}")

    if total_drafts:
        print(f"\nvalidate: NOTE: {total_drafts} definition(s) still `status: draft` "
              "(excluded from the eval 'perfect' baseline — not a failure).")

    if all_errors:
        print(f"\nvalidate: FAILED with {len(all_errors)} problem(s):", file=sys.stderr)
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"\nvalidate: OK — {total_docs} doc(s) validated, no schema errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
