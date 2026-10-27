#!/usr/bin/env python3
"""Reconcile a context repo against its upstream dbt lineage and flag stale context.

`context.config.yaml` is the drift seam: it maps each domain to the dbt model(s) its
context describes. This script computes the current column-set and test-set for every
referenced model (via scripts/dbt_extract.py) and diffs them against a committed
baseline (.ci/lineage-baseline.json). When a model's columns or tests change — or the
model disappears — the context written about it may now be stale, so we list the
affected objects and transitive consumers and exits non-zero. Reporting is read-only.
--prepare-patch writes a status-only proposal under ignored .nodal/drift; explicit
--apply-plan with its digest persists drafts and can resume an interrupted write.
Human approval metadata and the lineage baseline are preserved by status changes.

  # Establish/refresh the baseline (run once, then commit .ci/lineage-baseline.json):
  python .ci/drift.py --update-baseline --manifest dbt_core=target/manifest.json

  # Check for drift (CI default; exit 1 = drift found, exit 0 = clean):
  python .ci/drift.py --manifest dbt_core=target/manifest.json --out drift-report.md

  # Prepare, inspect, then explicitly apply exactly that status-only preview:
  python .ci/drift.py --manifest dbt_core=target/manifest.json --prepare-patch --json-out .nodal/drift-report.json
  python .ci/drift.py --apply-plan .nodal/drift/RUN_ID/plan.json --sha256 REVIEWED_DIGEST

Each `--manifest SOURCE_ID=PATH` supplies one lineage source's manifest (run
`dbt parse` in that repo first — no warehouse needed). A referenced source with no
manifest provided is reported as an unchecked coverage gap, never silently skipped.
Pass --fail-on-unchecked to turn that gap into a non-zero exit as well, so CI can
alert on it instead of quietly passing a run that evaluated nothing.

Exit codes: 0 = clean, 1 = drift found, 2 = setup error,
3 = no drift but ≥1 unchecked source (only with --fail-on-unchecked).

This script is deliberately free of any network/GitHub calls so it is fully testable
offline; the CI workflow owns manifest acquisition and issue creation.
"""
import argparse
import json
import sys
from pathlib import Path

# Reuse the manifest parser that already maps dbt -> column/test signal.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dbt_extract  # noqa: E402
from acf_runtime.loader import load_context
from acf_runtime.impact import lineage_impact, path_impact
from acf_runtime.drift import prepare, apply, render_impact

BASELINE_VERSION = 1
# Context files a domain may carry; we list whichever exist next to a drifted model.
DOMAIN_FILES = (
    "domain.yaml",
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
    if Path(path).name != "context.config.yaml":
        raise ValueError("drift requires the canonical context.config.yaml")
    registry = load_context(Path(path).resolve().parent)
    if registry.errors:
        raise ValueError("ACF 0.3 context must validate before drift analysis: " + ", ".join(sorted({d.code for d in registry.errors})))
    cfg = registry.config
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
    # Per-object and transitive lineage is authoritative even when the config's
    # optional domain convenience map was never populated.
    for node in registry.nodes.values():
        for source, model in node.lineage:
            referenced.setdefault(source, set()).add(model)
            if node.domain:
                domains.setdefault(node.domain, [])
                pair = (source, [model])
                if not any(s == source and model in models for s, models in domains[node.domain]):
                    domains[node.domain].append(pair)
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
        manifest = json.loads(Path(path).read_text())
        resources = {key: value for key, value in {**manifest.get("nodes", {}), **manifest.get("sources", {})}.items()
                     if value.get("resource_type") in ("model", "seed", "snapshot", "source")}
        aliases = {}
        for key, value in resources.items():
            aliases.setdefault(value["name"], []).append(key)
        sigs, absent = {}, []
        for model in sorted(referenced[source_id]):
            candidates = [model] if model in resources else aliases.get(model, [])
            if len(candidates) != 1:
                absent.append(model)  # absent or ambiguous short name, never guess
                continue
            key = candidates[0]
            value = resources[key]
            tests = []
            for test in manifest.get("nodes", {}).values():
                if test.get("resource_type") != "test" or test.get("attached_node") != key:
                    continue
                meta = test.get("test_metadata") or {}
                kind = dbt_extract._norm_test_name(meta.get("name"))
                if kind in dbt_extract.KNOWN_TESTS:
                    tests.append({"type": kind, "column": test.get("column_name"), "kwargs": meta.get("kwargs", {})})
            sigs[model] = model_signature({"columns": [{"name": col.get("name", name)}
                for name, col in (value.get("columns") or {}).items()], "tests": tests})
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
    return [f"domains/{domain}/{f}" for f in DOMAIN_FILES if (d / f).exists()] + [
        p.relative_to(repo_root).as_posix() for p in sorted((d / "metrics").glob("*.yaml"))]


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

    if drifted:
        header = "## Context drift detected"
    elif unchecked_sources:
        header = "## Context drift not fully evaluated"
    else:
        header = "## No context drift"
    out = [header, ""]
    if drifted:
        out += [
            "Upstream dbt models changed since the last reconciled baseline. Review the",
            "context files below, update them where the meaning changed, then refresh the",
            "baseline (`python .ci/drift.py --update-baseline ...`) and commit it.",
            "",
        ]
    elif unchecked_sources:
        out += [
            "No drift was found, but not every lineage source could be checked. Fix",
            "manifest acquisition for the sources below (publish a `dbt-manifest` branch",
            "from the dbt repo, or set DBT_REPO_TOKEN if it is private).",
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

def _parse_manifest_args(pairs, map_path=None):
    manifests = {}
    if map_path:
        from eval_harness.execution import strict_json
        manifests = strict_json(Path(map_path).read_text())
        if not isinstance(manifests, dict) or not all(
                isinstance(key, str) and key and isinstance(path, str) and path
                for key, path in manifests.items()):
            raise ValueError("--manifest-map must contain a JSON source-ID to path object")
    for pair in pairs or []:
        if "=" not in pair:
            _die(f"--manifest expects SOURCE_ID=PATH, got {pair!r}")
        source_id, path = pair.split("=", 1)
        if not source_id.strip() or not path.strip() or source_id.strip() in manifests:
            raise ValueError("manifest source IDs and paths must be nonempty; supply each source once")
        manifests[source_id.strip()] = path.strip()
    return manifests


def _write_output(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config",
                    help="path to context.config.yaml (default: ./context.config.yaml)")
    ap.add_argument("--baseline",
                    help="path to the committed baseline JSON")
    ap.add_argument("--manifest", action="append", metavar="SOURCE_ID=PATH",
                    help="manifest for one lineage source; repeatable")
    ap.add_argument("--manifest-map", help="JSON source-ID to path map from collect_manifests.py")
    ap.add_argument("--update-baseline", action="store_true",
                    help="write the current state to --baseline and exit 0")
    ap.add_argument("--fail-on-unchecked", action="store_true",
                    help="exit 3 when a referenced source has no manifest supplied")
    ap.add_argument("--out", help="also write the markdown report here")
    ap.add_argument("--repo-root", default=".",
                    help="repo root used to locate domains/ context files")
    ap.add_argument("--json-out", help="write structured impact and optional patch metadata")
    ap.add_argument("--prepare-patch", action="store_true", help="prepare status-only patch under ignored .nodal/drift; no authored writes")
    ap.add_argument("--apply-plan", help="explicitly apply/resume a prepared repo-relative .nodal/drift/<id>/plan.json")
    ap.add_argument("--sha256", help="exact reviewed plan digest required with --apply-plan")
    ap.add_argument("--changed-files", nargs="*", help="analyze authored context changes instead of upstream manifests")
    ap.add_argument("--base-root", help="base context directory for authored deletion/rename impact")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    args.config = args.config or str(repo_root / "context.config.yaml")
    args.baseline = args.baseline or str(repo_root / ".ci/lineage-baseline.json")
    if Path(args.config).resolve() != repo_root / "context.config.yaml":
        raise ValueError("--config must identify the selected context root's context.config.yaml")
    if args.apply_plan:
        if not args.sha256 or args.update_baseline or args.prepare_patch or args.changed_files is not None:
            raise ValueError("--apply-plan requires --sha256 and cannot be combined with detection/baseline mutation")
        result = apply(repo_root, args.apply_plan, args.sha256)
        print(json.dumps(result, indent=2))
        return 0
    if args.changed_files is not None:
        if args.update_baseline or args.manifest or args.manifest_map:
            raise ValueError("authored-change impact is separate from lineage baseline/manifest operations")
        impact = path_impact(repo_root, args.changed_files, base_root=args.base_root)
        registry = load_context(repo_root)
        affected = {item["id"] for item in impact["objects"]}
        impact["snapshot_batch"] = sorted(n.id for n in registry.seeds if n.id in affected
                                           and n.data["expected"]["kind"] == "value_at_snapshot")
        report = render_impact(impact)
        result = {"impact": impact, "status": "reported_not_applied"}
        if args.prepare_patch:
            if impact["fallback"]:
                raise ValueError("cannot prepare a precise patch from unresolved base/head graphs")
            result["patch"] = prepare(repo_root, impact, source_changes={"paths": sorted(args.changed_files)})
        if args.out:
            _write_output(args.out, report)
        if args.json_out:
            _write_output(args.json_out, json.dumps(result, indent=2) + "\n")
        print(report)
        if result.get("patch"):
            print(json.dumps(result["patch"], indent=2))
        return 1 if impact["objects"] else 0
    domains, referenced = load_config(args.config)
    if not referenced:
        _die(f"no domain lineage found in {args.config}; nothing to reconcile")

    manifests = _parse_manifest_args(args.manifest, args.manifest_map)
    current, missing_models, unchecked = compute_current(referenced, manifests)
    for s in unchecked:
        _warn(f"source {s!r} referenced but no manifest supplied; drift not evaluated")

    if args.update_baseline:
        if unchecked or missing_models:
            raise ValueError("baseline unchanged: supply all referenced models/sources before explicitly updating it")
        Path(args.baseline).parent.mkdir(parents=True, exist_ok=True)
        Path(args.baseline).write_text(
            json.dumps(build_baseline(current), indent=2, sort_keys=True) + "\n")
        print(f"drift: baseline written to {args.baseline}")
        return 0

    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        _die(f"baseline {args.baseline} not found; create it once with "
             "--update-baseline and commit it")
    baseline = json.loads(baseline_path.read_text())
    if not isinstance(baseline, dict) or baseline.get("version") != BASELINE_VERSION or not isinstance(baseline.get("sources"), dict):
        raise ValueError("unsupported or malformed lineage baseline")

    changes = diff_signatures(baseline, current)
    report, drifted = build_report(domains, changes, missing_models, unchecked, repo_root)
    registry = load_context(repo_root)
    if registry.errors:
        raise ValueError("context graph is invalid; cannot compute object-level drift")
    changed_models = {(source, model) for source, models in changes.items() for model in models}
    changed_models.update((source, model) for source, models in missing_models.items() for model in models)
    impact = lineage_impact(registry, changed_models)
    report += "\n" + render_impact(impact)
    result = {"impact": impact, "status": "reported_not_applied", "unchecked_sources": unchecked}
    if args.prepare_patch and drifted:
        result["patch"] = prepare(repo_root, impact, source_changes={"changes": changes, "missing_models": missing_models})
    from acf_runtime.governance import digest
    result["source_evidence"] = {}
    for source, path in manifests.items():
        if source not in unchecked:
            raw = Path(path).read_bytes()
            import hashlib
            fingerprint = hashlib.sha256(raw).hexdigest()
            result["source_evidence"][source] = {"status": "checked", "revision": "sha256:" + fingerprint, "digest": fingerprint}
    result["changes"] = changes
    if args.json_out:
        _write_output(args.json_out, json.dumps(result, indent=2) + "\n")
    print(report)
    if result.get("patch"):
        print(json.dumps(result["patch"], indent=2))
    if args.out:
        _write_output(args.out, report)
    if drifted:
        return 1
    if unchecked and args.fail_on_unchecked:
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(f"drift: ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
