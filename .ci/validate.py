#!/usr/bin/env python3
"""Validate ACF 0.3 context repos, or shipped examples and template structure.

Exit 0: valid; 1: invalid context; 2: configuration/dependency error.
Validation is read-only. Draft readiness issues warn; structural errors fail.
"""
import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acf_runtime.loader import discover_docs as _discover_docs, read_yaml, read_method, Schemas
from acf_runtime import load_context
from acf_runtime.observed import read_queue
from acf_runtime.expressions import MeasureParser

SCHEMA_FILE = {kind: kind + ".schema.json" for kind in
               ("config", "domain", "metric", "entity", "evalseed", "method", "shared")}


def discover_docs(root):
    return _discover_docs(root, templates=True)


def _load_yaml(path, yaml=None):
    try:
        return read_method(path)[0] if Path(path).suffix == ".md" else read_yaml(path)
    except Exception as exc:
        return exc


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
        if p.name == "metrics.yml":
            warns.append(f"{p}: legacy metric wrappers are unsupported in 0.3; convert to per-metric YAML before validation.")
        elif p.name in ("domain.yml", "entities.yml"):
            warns.append(
                f"{p}: consumers match '{p.stem}.yaml' exactly — this .yml "
                "variant is not validated or indexed; rename to .yaml.")
    return warns


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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("roots", nargs="*")
    ap.add_argument("--branch-test", action="store_true", help="validate proposed context without granting approval")
    ap.add_argument("--require-ready", action="store_true", help="fail on unresolved dependencies/readiness blockers before merge")
    ap.add_argument("--schemas")
    ap.add_argument("--manifest", action="append", default=[], metavar="SOURCE_ID=PATH")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    schema_dir = Path(args.schemas) if args.schemas else Path(__file__).resolve().parents[1] / "schemas"
    manifests = {}
    try:
        for pair in args.manifest:
            source, sep, path = pair.partition("=")
            if not source or not sep or not path:
                raise ValueError("--manifest expects SOURCE_ID=PATH")
            manifest = json.loads(Path(path).read_text())
            if not isinstance(manifest, dict) or any(not isinstance(manifest.get(k, {}), dict) for k in ("nodes", "sources")):
                raise ValueError("manifest must contain nodes/sources objects")
            manifests[source] = manifest
        checker = Schemas(schema_dir)
        strict, structural = ([Path(r) for r in args.roots], None) if args.roots else discover_roots()
        diagnostics = []
        total = 0
        for root in strict:
            registry = load_context(root, schemas=schema_dir, manifests=manifests, branch_test=True if args.branch_test else None)
            diagnostics.extend(vars(d) for d in registry.diagnostics)
            if args.require_ready and (args.roots or Path("context.config.yaml").is_file()):
                for node in registry.nodes.values():
                    if node.blocking_reasons:
                        diagnostics.append(dict(code="merge.blocked", severity="error", path=node.path, field="",
                            message=", ".join(sorted(node.blocking_reasons)), target=node.id))
            try:
                read_queue(root, checker, registry)
            except (ValueError, OSError) as exc:
                diagnostics.append(dict(code="observed.invalid", severity="error",
                    path=str(root / "evals/observed/queue.jsonl"), field="", message=str(exc), target=""))
            docs = discover_docs(root)
            total += len(docs)
            warnings = lineage_repo_warnings(docs, None) + entity_placement_warnings(docs, None, root) + canonical_name_warnings(root)
            diagnostics.extend(dict(code="context.warning", severity="warning", path=str(root), field="", message=w, target="") for w in warnings)
        if structural:
            docs = discover_docs(structural)
            total += len(docs)
            for error in check_structure(docs, checker.raw, None):
                diagnostics.append(dict(code="template.structure", severity="error", path=str(structural), field="", message=error, target=""))
        errors = sum(d["severity"] == "error" for d in diagnostics)
        if args.json:
            print(json.dumps({"schema_version": 1, "documents": total, "errors": errors, "diagnostics": diagnostics}, indent=2))
        else:
            for d in diagnostics:
                print(f"validate: {d['severity'].upper()} {d['path']}:{d['field']} [{d['code']}] {d['message']}")
                for related in d.get("related", []):
                    print(f"  related: {related['path']}:{related['field']}")
            print(f"validate: {'FAILED' if errors else 'OK'} — {total} documents, {errors} errors")
        return 1 if errors else 0
    except (ImportError, OSError, ValueError) as exc:
        print(f"validate: setup error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
