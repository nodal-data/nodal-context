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
        if isinstance(doc, dict) and doc.get("status") == "draft":
            drafts += 1
        v = validator_cls(schemas[kind], registry=registry)
        for err in sorted(v.iter_errors(doc), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "(root)"
            errors.append(f"{path} [{kind}] at {loc}: {err.message}")
    return errors, drafts


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
    ap.add_argument("--schemas", help="path to schemas/ (default: ./schemas or beside .ci/)")
    args = ap.parse_args(argv)

    try:
        import yaml, jsonschema
        from referencing import Registry, Resource
    except ImportError as e:
        _die(f"missing dependency ({e}); run: pip install jsonschema pyyaml")

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

    all_errors, total_docs, total_drafts = [], 0, 0

    for root in strict_roots:
        docs = discover_docs(root)
        total_docs += len(docs)
        errs, drafts = validate_strict(docs, raw, validator_cls, registry, yaml)
        total_drafts += drafts
        all_errors += errs
        print(f"validate: {root}/ — {len(docs)} doc(s), "
              f"{len(errs)} error(s), {drafts} draft(s)")

    if structural_root:
        docs = discover_docs(structural_root)
        total_docs += len(docs)
        errs = check_structure(docs, raw, yaml)
        all_errors += errs
        print(f"validate: {structural_root}/ — {len(docs)} doc(s) (structural), "
              f"{len(errs)} error(s)")

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
