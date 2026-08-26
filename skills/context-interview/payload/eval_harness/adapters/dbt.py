"""dbt adapter: a dbt project (or a manifest.json) -> NCR.

Context comes from what dbt already documents: model + column descriptions, grain
evidence from unique tests, accepted values, and — manifest only — semantic models and
metrics (manifest schema v12; earlier versions simply lack those keys). Parsing
conventions mirror scripts/dbt_extract.py, but where the extractor emits draft findings
for the interview, this adapter assembles the context-on payload.

`--root` may be a manifest.json path or a dbt project directory (target/manifest.json is
used when present; otherwise the models/**/*.yml properties files are read directly —
that fallback needs PyYAML, the manifest branch is stdlib-only).

Domain mapping: a model's top-level folder under models/ (e.g. `marts`, `staging`);
models at the models/ root fall back to the project name. Semantic models and metrics
are project-level, so they're appended to every domain.

dbt docs are context, not ground truth, so the NCR has no seeds — attach them with the
runner's `--seeds` flag (see INTERFACE.md).
"""
import json
from pathlib import Path

from ..ncr import NCR

_GRAIN_TESTS = {"unique", "unique_combination_of_columns"}


def _norm_test_name(name):
    return (name or "").split(".")[-1]


def _model_text(m: dict) -> str:
    lines = [f"## Model: {m['name']}" + (f"  ({m['relation']})" if m.get("relation") else "")]
    if m.get("description"):
        lines.append(m["description"])
    if m.get("grain_hints"):
        lines.append(f"Grain (from unique tests): {'; '.join(m['grain_hints'])}")
    cols = [c for c in m.get("columns", []) if c.get("description")]
    if cols:
        lines.append("Columns:")
        lines += [f"  - {c['name']}: {c['description']}" for c in cols]
    if m.get("accepted_values"):
        lines.append("Accepted values:")
        lines += [f"  - {col} in ({', '.join(str(v) for v in vals)})"
                  for col, vals in m["accepted_values"]]
    return "\n".join(lines)


def _semantic_text(manifest: dict) -> str:
    """Semantic models + metrics (manifest v12) -> one shared block."""
    lines = []
    sems = [s for s in (manifest.get("semantic_models") or {}).values() if s.get("name")]
    if sems:
        lines.append("# Semantic models")
        for s in sems:
            lines.append(f"## {s['name']}" + (f": {s['description'].strip()}"
                                              if s.get("description") else ""))
            for key in ("entities", "dimensions", "measures"):
                names = [e.get("name") for e in s.get(key) or [] if e.get("name")]
                if names:
                    lines.append(f"  {key}: {', '.join(names)}")
    mets = [m for m in (manifest.get("metrics") or {}).values() if m.get("name")]
    if mets:
        lines.append("# Metrics (governed definitions)")
        for m in mets:
            head = f"- {m['name']}" + (f" [{m['type']}]" if m.get("type") else "")
            if m.get("description"):
                head += f": {m['description'].strip()}"
            lines.append(head)
            if m.get("filter"):
                f = m["filter"]
                expr = f.get("where_sql_template") if isinstance(f, dict) else f
                if expr:
                    lines.append(f"    filter: {expr}")
    return "\n".join(lines)


def _from_manifest(manifest: dict):
    """-> (models_by_name with domain, shared semantic/metric text)"""
    project = manifest.get("metadata", {}).get("project_name", "dbt")
    models = {}
    for v in manifest.get("nodes", {}).values():
        if v.get("resource_type") != "model":
            continue
        fqn = v.get("fqn") or []
        models[v["name"]] = {
            "name": v["name"],
            "relation": v.get("relation_name"),
            "description": (v.get("description") or "").strip(),
            "columns": [{"name": c.get("name"),
                         "description": (c.get("description") or "").strip()}
                        for c in (v.get("columns") or {}).values()],
            "domain": fqn[1] if len(fqn) >= 3 else project,
            "grain_hints": [],
            "accepted_values": [],
        }
    for v in manifest.get("nodes", {}).values():
        if v.get("resource_type") != "test":
            continue
        tm = v.get("test_metadata") or {}
        ttype = _norm_test_name(tm.get("name"))
        target = (v.get("attached_node") or "").split(".")[-1]
        if target not in models:
            continue
        kwargs = tm.get("kwargs") or {}
        if ttype == "unique" and v.get("column_name"):
            models[target]["grain_hints"].append(v["column_name"])
        elif ttype == "unique_combination_of_columns":
            cols = kwargs.get("combination_of_columns") or []
            if cols:
                models[target]["grain_hints"].append(" + ".join(cols))
        elif ttype == "accepted_values" and v.get("column_name") and kwargs.get("values"):
            models[target]["accepted_values"].append((v["column_name"], kwargs["values"]))
    return models, _semantic_text(manifest)


def _from_source(project_dir: Path):
    import yaml
    models_dir = project_dir / "models"
    models = {}
    for yml in sorted(models_dir.rglob("*.yml")) + sorted(models_dir.rglob("*.yaml")):
        try:
            doc = yaml.safe_load(yml.read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        rel = yml.parent.relative_to(models_dir)
        domain = rel.parts[0] if rel.parts else project_dir.name
        for mdl in doc.get("models", []) or []:
            if not mdl.get("name"):
                continue
            models[mdl["name"]] = {
                "name": mdl["name"],
                "relation": None,
                "description": (mdl.get("description") or "").strip(),
                "columns": [{"name": c.get("name"),
                             "description": (c.get("description") or "").strip()}
                            for c in mdl.get("columns", []) or []],
                "domain": domain,
                "grain_hints": [],
                "accepted_values": [],
            }
    return models, ""


def build_ncr(root, domains=None) -> NCR:
    root = Path(root)
    manifest_path = next((p for p in (root, root / "target" / "manifest.json",
                                      root / "manifest.json") if p.is_file()), None)
    if manifest_path:
        models, shared = _from_manifest(json.loads(manifest_path.read_text()))
    else:
        models, shared = _from_source(root)

    by_domain = {}
    for m in models.values():
        by_domain.setdefault(m["domain"], []).append(m)

    context_by_domain = {}
    for domain, ms in sorted(by_domain.items()):
        if domains and domain not in domains:
            continue
        blocks = ([f"# dbt context — {domain}"]
                  + [_model_text(m) for m in sorted(ms, key=lambda m: m["name"])]
                  + [shared])
        context_by_domain[domain] = "\n\n".join(b for b in blocks if b)

    return NCR(seeds=[], context_by_domain=context_by_domain)
