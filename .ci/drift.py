#!/usr/bin/env python3
"""Reconcile a context repo against its upstream dbt lineage and flag stale context.

`context.config.yaml` is the drift seam: it maps each domain to the dbt model(s) its
context describes. This script computes the current column-set and test-set for every
referenced model (via scripts/dbt_extract.py) and diffs them against a committed
baseline (.ci/lineage-baseline.json). When a model's columns or tests change — or the
model disappears — the context written about it may now be stale, so we list the
affected domains and their context files and exit non-zero. CI turns that into an issue.

  # Establish/refresh the baseline (run once, then commit .ci/lineage-baseline.json):
  python .ci/drift.py --update-baseline --manifest dbt_core=target/manifest.json

  # Check for drift (CI default; exit 1 = drift found, exit 0 = clean):
  python .ci/drift.py --manifest dbt_core=target/manifest.json --out drift-report.md

Each `--manifest SOURCE_ID=PATH` supplies one lineage source's manifest (run
`dbt parse` in that repo first — no warehouse needed). A referenced source with no
manifest provided is reported as an unchecked coverage gap, never silently skipped.

This script is deliberately free of any network/GitHub calls so it is fully testable
offline; the CI workflow owns manifest acquisition and issue creation.
"""
import argparse
import json
import sys
from pathlib import Path

# Reuse the manifest parser that already maps dbt -> column/test signal.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dbt_extract  # noqa: E402

BASELINE_VERSION = 1
# Context files a domain may carry; we list whichever exist next to a drifted model.
DOMAIN_FILES = (
    "domain.yaml",
    "metrics.yaml",
    "entities.yaml",
    "reference.md",
    "known-issues.md",
    "context.md",
)


def _warn(msg):
    print(f"drift: WARNING: {msg}", file=sys.stderr)


def _die(msg, code=2):
    print(f"drift: ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


# ----- signatures -------------------------------------------------------------

def _test_sig(t):
    """Stable string for one mapped dbt test, so a changed test registers as drift.

    Captures the discriminating kwargs (accepted_values list, relationship target,
    composite-grain columns) — not just the test type — because changing those is a
    real semantic change the context may describe.
    """
    parts = [t["type"]]
    if t.get("column"):
        parts.append(t["column"])
    kw = t.get("kwargs") or {}
    if t["type"] == "unique_combination_of_columns":
        parts.append("+".join(kw.get("combination_of_columns") or []))
    elif t["type"] == "accepted_values":
        parts.append("[" + ",".join(str(v) for v in (kw.get("values") or [])) + "]")
    elif t["type"] == "relationships":
        parts.append(f"->{kw.get('to')}.{kw.get('field')}")
    return ":".join(str(p) for p in parts)


def model_signature(m):
    """{columns: sorted names, tests: sorted unique test sigs} for one dbt model."""
    return {
        "columns": sorted(c["name"] for c in m["columns"] if c.get("name")),
        "tests": sorted({_test_sig(t) for t in m["tests"]}),
    }


# ----- config -----------------------------------------------------------------

def load_config(path):
    """Parse context.config.yaml into the domain->lineage map drift iterates.

    Returns (domains, referenced):
      domains    : {domain_name: [(source_id, [model, ...]), ...]}
      referenced : {source_id: set(model_names)}  (union across all domains)
    """
    try:
        import yaml
    except ImportError:
        _die("context.config.yaml parsing needs PyYAML (pip install pyyaml)")
    cfg = yaml.safe_load(Path(path).read_text()) or {}
    domains, referenced = {}, {}
    for name, spec in (cfg.get("domains") or {}).items():
        entries = []
        for entry in (spec or {}).get("lineage", []) or []:
            source_id = entry.get("source")
            models = list(entry.get("models") or [])
            if not source_id or not models:
                continue
            entries.append((source_id, models))
            referenced.setdefault(source_id, set()).update(models)
        if entries:
            domains[name] = entries
    return domains, referenced


# ----- current state + diff ---------------------------------------------------

def compute_current(referenced, manifests):
    """Signatures for every referenced model we can see in a provided manifest.

    Returns (current, missing_models, unchecked_sources):
      current          : {source_id: {model: signature}}
      missing_models   : {source_id: [referenced models absent from the manifest]}
      unchecked_sources: [source_ids referenced but with no manifest supplied]
    """
    current, missing_models, unchecked_sources = {}, {}, []
    for source_id in sorted(referenced):
        path = manifests.get(source_id)
        if not path:
            unchecked_sources.append(source_id)
            continue
        findings = dbt_extract.from_manifest(json.loads(Path(path).read_text()))
        by_name = {m["name"]: m for m in findings["models"]}
        sigs, absent = {}, []
        for model in sorted(referenced[source_id]):
            if model in by_name:
                sigs[model] = model_signature(by_name[model])
            else:
                absent.append(model)
        current[source_id] = sigs
        if absent:
            missing_models[source_id] = absent
    return current, missing_models, unchecked_sources


def diff_signatures(baseline, current):
    """Per (source, model) change record vs the baseline. Empty dict == no drift."""
    changes = {}
    b_sources = baseline.get("sources", {})
    for source_id, models in current.items():
        b_models = b_sources.get(source_id, {}).get("models", {})
        for model, sig in models.items():
            b_sig = b_models.get(model)
            if b_sig is None:
                changes.setdefault(source_id, {})[model] = {"new_model": True}
                continue
            rec = {
                "columns_added": sorted(set(sig["columns"]) - set(b_sig.get("columns", []))),
                "columns_removed": sorted(set(b_sig.get("columns", [])) - set(sig["columns"])),
                "tests_added": sorted(set(sig["tests"]) - set(b_sig.get("tests", []))),
                "tests_removed": sorted(set(b_sig.get("tests", [])) - set(sig["tests"])),
            }
            if any(rec.values()):
                changes.setdefault(source_id, {})[model] = rec
    return changes


def build_baseline(current):
    return {
        "version": BASELINE_VERSION,
        "sources": {
            source_id: {"models": sigs} for source_id, sigs in sorted(current.items())
        },
    }


# ----- reporting --------------------------------------------------------------

def _domain_files(repo_root, domain):
    d = repo_root / "domains" / domain
    return [f"domains/{domain}/{f}" for f in DOMAIN_FILES if (d / f).exists()]


def _model_lines(rec):
    lines = []
    if rec.get("new_model"):
        lines.append("    - newly tracked model (no prior baseline)")
        return lines
    for label, key in (
        ("columns added", "columns_added"),
        ("columns removed", "columns_removed"),
        ("tests added", "tests_added"),
        ("tests removed", "tests_removed"),
    ):
        if rec.get(key):
            lines.append(f"    - {label}: {', '.join(rec[key])}")
    return lines


def build_report(domains, changes, missing_models, unchecked_sources, repo_root):
    """Markdown report grouped by domain. Returns (text, drifted_bool)."""
    # Reverse-map (source, model) -> change/missing so we can group by domain.
    missing_set = {(s, m) for s, ms in missing_models.items() for m in ms}
    drifted = bool(changes) or bool(missing_set)

    out = ["## Context drift detected" if drifted else "## No context drift", ""]
    if drifted:
        out += [
            "Upstream dbt models changed since the last reconciled baseline. Review the",
            "context files below, update them where the meaning changed, then refresh the",
            "baseline (`python .ci/drift.py --update-baseline ...`) and commit it.",
            "",
        ]

    for domain in sorted(domains):
        domain_blocks = []
        for source_id, models in domains[domain]:
            for model in models:
                rec = changes.get(source_id, {}).get(model)
                if rec:
                    block = [f"  - **{model}** ({source_id})"] + _model_lines(rec)
                    domain_blocks.append("\n".join(block))
                elif (source_id, model) in missing_set:
                    domain_blocks.append(
                        f"  - **{model}** ({source_id}) — no longer present in dbt "
                        "(renamed or removed); context here is almost certainly stale"
                    )
        if domain_blocks:
            files = _domain_files(repo_root, domain) or ["(no context files found)"]
            out.append(f"### domain: {domain}")
            out.append(f"_Affected context files: {', '.join(files)}_")
            out += domain_blocks
            out.append("")

    if unchecked_sources:
        out.append("### Unchecked lineage sources")
        out.append(
            "These sources are referenced in `context.config.yaml` but no manifest was "
            "supplied, so drift could not be evaluated for them:"
        )
        out += [f"  - {s}" for s in unchecked_sources]
        out.append("")

    return "\n".join(out).rstrip() + "\n", drifted


# ----- main -------------------------------------------------------------------

def _parse_manifest_args(pairs):
    manifests = {}
    for pair in pairs or []:
        if "=" not in pair:
            _die(f"--manifest expects SOURCE_ID=PATH, got {pair!r}")
        source_id, path = pair.split("=", 1)
        manifests[source_id.strip()] = path.strip()
    return manifests


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="context.config.yaml",
                    help="path to context.config.yaml (default: ./context.config.yaml)")
    ap.add_argument("--baseline", default=".ci/lineage-baseline.json",
                    help="path to the committed baseline JSON")
    ap.add_argument("--manifest", action="append", metavar="SOURCE_ID=PATH",
                    help="manifest for one lineage source; repeatable")
    ap.add_argument("--update-baseline", action="store_true",
                    help="write the current state to --baseline and exit 0")
    ap.add_argument("--out", help="also write the markdown report here")
    ap.add_argument("--repo-root", default=".",
                    help="repo root used to locate domains/ context files")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root)
    domains, referenced = load_config(args.config)
    if not referenced:
        _die(f"no domain lineage found in {args.config}; nothing to reconcile")

    manifests = _parse_manifest_args(args.manifest)
    current, missing_models, unchecked = compute_current(referenced, manifests)
    for s in unchecked:
        _warn(f"source {s!r} referenced but no manifest supplied; drift not evaluated")

    if args.update_baseline:
        if unchecked:
            _warn("writing baseline with unchecked sources omitted — supply all "
                  "manifests for a complete baseline")
        Path(args.baseline).write_text(
            json.dumps(build_baseline(current), indent=2, sort_keys=True) + "\n")
        print(f"drift: baseline written to {args.baseline}")
        return 0

    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        _die(f"baseline {args.baseline} not found; create it once with "
             "--update-baseline and commit it")
    baseline = json.loads(baseline_path.read_text())

    changes = diff_signatures(baseline, current)
    report, drifted = build_report(domains, changes, missing_models, unchecked, repo_root)
    print(report)
    if args.out:
        Path(args.out).write_text(report)
    return 1 if drifted else 0


if __name__ == "__main__":
    raise SystemExit(main())
