#!/usr/bin/env python3
"""Extract *draft* context signal from a dbt project into a compact dbt-findings.json.

  Primary  (run `dbt parse` first — no warehouse needed):
      python3 scripts/dbt_extract.py --manifest path/to/target/manifest.json
  Fallback (bare clone, can't produce a manifest):
      python3 scripts/dbt_extract.py --source path/to/dbt_project_dir

The interview agent (Stage 0) maps this summary to ACF stubs — all `status: draft`,
tagged `# dbt-derived` — which the analyst then confirms. NOTHING here is ground
truth: dbt descriptions are often stale/aspirational. The `unavailable` list tells
the agent what dbt did NOT provide, so it elicits those by hand instead of skipping.

The manifest branch is stdlib-only. The --source fallback needs PyYAML.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Test names we map to ACF (namespace-stripped). Everything else is ignored.
GRAIN_TESTS = {"unique", "unique_combination_of_columns"}
KNOWN_TESTS = GRAIN_TESTS | {"not_null", "accepted_values", "relationships"}
SUPPORTED_SCHEMA = "v11"  # dbt 1.7; other recent versions warn but still parse.


def _warn(msg):
    print(f"dbt_extract: WARNING: {msg}", file=sys.stderr)


def _norm_test_name(name):
    """Strip dbt-pkg namespace: 'dbt_utils.unique_combination_of_columns' -> short."""
    return (name or "").split(".")[-1]


def _model_short(node_id):
    """'model.veritas_dbt.fct_session_financials' -> 'fct_session_financials'."""
    return node_id.split(".")[-1] if node_id else None


def _grain_hint(tests):
    """Headline win: turn unique / unique_combination tests into a grain candidate."""
    hints = []
    for t in tests:
        if t["type"] == "unique" and t.get("column"):
            hints.append(t["column"])
        elif t["type"] == "unique_combination_of_columns":
            cols = (t.get("kwargs") or {}).get("combination_of_columns") or []
            if cols:
                hints.append(" + ".join(cols))
    return hints


def _finalize(models_by_name, exposures, source, schema_version, dbt_version):
    """Common assembly: per-model grain hints, sort, compute unavailable[]/coverage."""
    models = []
    for name in sorted(models_by_name):
        m = models_by_name[name]
        m["tests"].sort(key=lambda t: (t["type"], t.get("column") or ""))
        m["depends_on"] = sorted(set(m["depends_on"]))
        m["grain_hint"] = _grain_hint(m["tests"])
        models.append(m)

    seen_test_types = {t["type"] for m in models for t in m["tests"]}
    unavailable = []
    if not exposures:
        unavailable.append("exposures")
    for tt in ("accepted_values", "relationships"):
        if tt not in seen_test_types:
            unavailable.append(tt)

    n = len(models) or 1
    coverage = {
        "models": len(models),
        "with_description": sum(1 for m in models if m["description"]),
        "with_column_descriptions": sum(
            1 for m in models if any(c.get("description") for c in m["columns"])
        ),
        "with_grain_evidence": sum(1 for m in models if m["grain_hint"]),
    }
    return {
        "source": source,
        "dbt_schema_version": schema_version,
        "dbt_version": dbt_version,
        "compiled_sql": any(m.get("has_compiled_sql") for m in models),
        "models": models,
        "exposures": sorted(exposures, key=lambda e: e.get("name") or ""),
        "unavailable": unavailable,
        "coverage": coverage,
    }


def from_manifest(manifest):
    meta = manifest.get("metadata", {})
    schema_version = meta.get("dbt_schema_version", "")
    if SUPPORTED_SCHEMA not in schema_version:
        _warn(
            f"manifest schema {schema_version!r} is not the tested {SUPPORTED_SCHEMA}; "
            "node shapes are usually stable, proceeding."
        )

    nodes = manifest.get("nodes", {})
    models_by_name = {}
    for nid, v in nodes.items():
        if v.get("resource_type") != "model":
            continue
        name = v["name"]
        models_by_name[name] = {
            "name": name,
            "relation": v.get("relation_name"),
            "description": (v.get("description") or "").strip(),
            "columns": [
                {"name": c.get("name"), "description": (c.get("description") or "").strip()}
                for c in (v.get("columns") or {}).values()
            ],
            "depends_on": [
                _model_short(d)
                for d in (v.get("depends_on", {}).get("nodes") or [])
                if d.startswith("model.")
            ],
            "tests": [],
            "has_sql": bool(v.get("raw_code") or v.get("compiled_code")),
            "has_compiled_sql": bool(v.get("compiled_code")),
        }

    # Attach tests to their model via attached_node (skip source/custom tests).
    for v in nodes.values():
        if v.get("resource_type") != "test":
            continue
        tm = v.get("test_metadata") or {}
        ttype = _norm_test_name(tm.get("name"))
        if ttype not in KNOWN_TESTS:
            continue  # custom/singular tests carry no ACF-mappable structure
        target = _model_short(v.get("attached_node"))
        if not target or target not in models_by_name:
            continue
        kwargs = tm.get("kwargs") or {}
        entry = {"type": ttype, "column": v.get("column_name")}
        if ttype == "unique_combination_of_columns":
            entry["kwargs"] = {"combination_of_columns": kwargs.get("combination_of_columns")}
        elif ttype == "accepted_values":
            entry["kwargs"] = {"values": kwargs.get("values")}
        elif ttype == "relationships":
            entry["kwargs"] = {"to": kwargs.get("to"), "field": kwargs.get("field")}
        models_by_name[target]["tests"].append(entry)

    exposures = []
    for e in manifest.get("exposures", {}).values():
        exposures.append({
            "name": e.get("name"),
            "label": e.get("label"),
            "url": e.get("url"),
            "owner": (e.get("owner") or {}).get("name") or (e.get("owner") or {}).get("email"),
            "maturity": e.get("maturity"),
            "depends_on": sorted(
                _model_short(d)
                for d in (e.get("depends_on", {}).get("nodes") or [])
                if d.startswith("model.")
            ),
        })

    return _finalize(
        models_by_name, exposures, "manifest", schema_version, meta.get("dbt_version")
    )


# ----- source-file fallback (metadata-first; no Jinja SQL filter extraction) -----

REF_RE = re.compile(r"""\bref\(\s*['"]([^'"]+)['"]""")
SOURCE_RE = re.compile(r"""\bsource\(\s*['"][^'"]+['"]\s*,\s*['"]([^'"]+)['"]""")


def _parse_yml_tests(test_list, column=None):
    """dbt schema-yml tests -> our normalized test entries (strings or dicts)."""
    out = []
    for t in test_list or []:
        if isinstance(t, str):
            ttype = _norm_test_name(t)
            if ttype in KNOWN_TESTS:
                out.append({"type": ttype, "column": column})
        elif isinstance(t, dict):
            for raw_name, cfg in t.items():
                ttype = _norm_test_name(raw_name)
                if ttype not in KNOWN_TESTS:
                    continue
                cfg = cfg or {}
                entry = {"type": ttype, "column": column}
                if ttype == "unique_combination_of_columns":
                    entry["kwargs"] = {"combination_of_columns": cfg.get("combination_of_columns")}
                elif ttype == "accepted_values":
                    entry["kwargs"] = {"values": cfg.get("values")}
                elif ttype == "relationships":
                    entry["kwargs"] = {"to": cfg.get("to"), "field": cfg.get("field")}
                out.append(entry)
    return out


def from_source(dbt_dir):
    try:
        import yaml
    except ImportError:
        print("dbt_extract: --source needs PyYAML (pip install pyyaml)", file=sys.stderr)
        sys.exit(2)

    dbt_dir = Path(dbt_dir)
    models_dir = dbt_dir / "models"
    if not models_dir.exists():
        print(f"dbt_extract: no models/ under {dbt_dir}", file=sys.stderr)
        sys.exit(2)

    models_by_name = {}

    # 1) Properties YAML: descriptions + tests (model- and column-level).
    for yml in sorted(models_dir.rglob("*.yml")) + sorted(models_dir.rglob("*.yaml")):
        try:
            doc = yaml.safe_load(yml.read_text()) or {}
        except yaml.YAMLError as e:
            _warn(f"could not parse {yml}: {e}")
            continue
        for mdl in doc.get("models", []) or []:
            name = mdl.get("name")
            if not name:
                continue
            entry = models_by_name.setdefault(name, _empty_source_model(name))
            if mdl.get("description"):
                entry["description"] = mdl["description"].strip()
            entry["tests"] += _parse_yml_tests(mdl.get("tests"))  # model-level
            for col in mdl.get("columns", []) or []:
                cname = col.get("name")
                if col.get("description"):
                    entry["columns"].append(
                        {"name": cname, "description": col["description"].strip()}
                    )
                entry["tests"] += _parse_yml_tests(col.get("tests"), column=cname)

    # 2) Model SQL: dependency graph from ref()/source() (no filter scraping).
    for sql in sorted(models_dir.rglob("*.sql")):
        name = sql.stem
        entry = models_by_name.setdefault(name, _empty_source_model(name))
        entry["has_sql"] = True
        text = sql.read_text()
        deps = set(REF_RE.findall(text))
        entry["depends_on"] += sorted(deps)

    # Keep depends_on entries that resolve to known models (drop sources/seeds).
    known = set(models_by_name)
    for m in models_by_name.values():
        m["depends_on"] = [d for d in m["depends_on"] if d in known]

    # Source-mode manifests never carry exposures.
    return _finalize(models_by_name, [], "source", None, None)


def _empty_source_model(name):
    return {
        "name": name,
        "relation": None,
        "description": "",
        "columns": [],
        "depends_on": [],
        "tests": [],
        "has_sql": False,
        "has_compiled_sql": False,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--manifest", help="path to target/manifest.json (run `dbt parse` first)")
    g.add_argument("--source", help="path to a dbt project dir (fallback, no manifest)")
    ap.add_argument("-o", "--out", help="write JSON here instead of stdout")
    args = ap.parse_args(argv)

    if args.manifest:
        findings = from_manifest(json.loads(Path(args.manifest).read_text()))
    else:
        findings = from_source(args.source)

    text = json.dumps(findings, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
