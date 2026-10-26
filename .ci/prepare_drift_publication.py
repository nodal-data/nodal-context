#!/usr/bin/env python3
"""Build a checked publication payload and public patch; no remote or authored writes."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime.drift import baseline_hash, encoded, sha, status_edits, overlay
from acf_runtime.impact import commit, git, snapshot
from acf_runtime.loader import load_context
from acf_runtime.observed_review import documents, schema_hash, schema_dir
from acf_runtime.regrade import approved_history, check_seeds, fingerprints
from acf_runtime.verified import contained, atomic_private
from eval_harness.execution import strict_json
from eval_harness import client


def regraded_edits(root, edits, selected, provider):
    """Check the proposed graph, preserving pending definition review as blockers."""
    initial = fingerprints(root)
    contents = documents(root)
    registry = load_context(root)
    previous = approved_history(root, registry.seeds)
    with overlay(root, contents, edits) as proposed:
        # Re-grading and NCR rendering use the same trusted current schemas.
        shutil.copytree(schema_dir(root), proposed.root / "schemas")
        evidence, report = check_seeds(proposed.root, previous, seed_ids=selected, provider=provider)
        eligible = {r["seed"] for r in evidence["checks"] if r["eligible"]}
        restored = status_edits(proposed, eligible, status="confirmed")
        final = {e["path"]: e["after"] for e in [*edits, *restored]}
    if fingerprints(root) != initial:
        raise ValueError("context changed while preparing fresh re-grades")
    # Never persist the temporary overlay path as provenance; hashes describe the
    # proposed graph, and the source fingerprints bind it to the checked-out repo.
    evidence["source_fingerprints"] = initial
    evidence_path = contained(root, ".nodal/regrades/ci-" + uuid.uuid4().hex + "/evidence.json", ".nodal/regrades")
    atomic_private(evidence_path, encoded(evidence))
    result = []
    for name, after in sorted(final.items()):
        before = contents[name].decode()
        if before != after:
            result.append({"path": name, "before": before, "after": after,
                           "before_sha256": sha(before.encode()), "after_sha256": sha(after.encode())})
    with overlay(root, contents, result):
        pass
    return result, report


def prepare_publication(root, report_path, base_ref, *, regrade=False, provider=client):
    root = Path(root).resolve()
    report = strict_json(contained(root, report_path, ".nodal").read_text())
    base_sha = commit(root, "HEAD")
    payload = {"version": 1, "baseRef": base_ref, "baseSha": base_sha, "edits": [],
               "batch": "unchecked", "report": "", "patch": ""}
    if not base_ref or base_ref.startswith("-") or any(ord(c) < 32 for c in base_ref):
        raise ValueError("invalid base branch")
    preview = report.get("patch")
    checks = None
    edits = []
    if preview:
        path = contained(root, preview["plan"], ".nodal/drift")
        raw = path.read_bytes()
        if sha(raw) != preview["sha256"]:
            raise ValueError("drift plan changed before publication")
        plan = strict_json(raw.decode())
        if not re.fullmatch(r"[a-f0-9]{20}", plan["batch"]):
            raise ValueError("invalid drift batch")
        contents = documents(root)
        if ({name: sha(raw) for name, raw in contents.items()} != plan["context"] or
                schema_hash(root) != plan["schemas"] or baseline_hash(root) != plan["baseline_sha256"]):
            raise ValueError("context, schema or baseline changed before publication")
        registry = load_context(root)
        if registry.errors or status_edits(registry, plan["objects"]) != plan["edits"]:
            raise ValueError("only validated status-only drift changes may be published")
        with snapshot(root, base_sha) as original:
            if documents(original) != contents:
                raise ValueError("publication requires context matching the checked-out commit")
        if sha(git(root, "show", base_sha + ":.ci/lineage-baseline.json")) != plan["baseline_sha256"]:
            raise ValueError("publication requires the committed lineage baseline")
        edits = plan["edits"]
        if regrade:
            selected = [key for key in plan["objects"] if registry.nodes[key].kind == "evalseed"]
            edits, checks = regraded_edits(root, edits, selected, provider)
        payload["batch"] = plan["batch"]
    elif regrade and not report.get("unchecked_sources"):
        with snapshot(root, base_sha) as original:
            if documents(original) != documents(root):
                raise ValueError("publication requires context matching the checked-out commit")
        edits, checks = regraded_edits(root, [], None, provider)
        payload["purpose"] = "seed-regrade"
        payload["batch"] = sha(encoded({"context": fingerprints(root), "edits": edits}))[:20]
    modes = {}
    for entry in git(root, "ls-tree", "-r", "-z", base_sha).split(b"\0"):
        if entry:
            header, name = entry.split(b"\t", 1)
            modes[name.decode()] = header.decode().split()[0]
    if edits:
        tracked_baseline = modes.get(".ci/lineage-baseline.json")
        committed = sha(git(root, "show", base_sha + ":.ci/lineage-baseline.json")) if tracked_baseline else None
        if tracked_baseline not in (None, "100644", "100755") or committed != baseline_hash(root):
            raise ValueError("publication requires the committed lineage baseline")
    for edit in edits:
        mode = modes.get(edit["path"])
        if mode not in ("100644", "100755"):
            raise ValueError("publication target must be a tracked regular file")
        payload["edits"].append({"path": edit["path"], "mode": mode, "type": "blob", "content": edit["after"]})
    payload["patch"] = "".join("".join(difflib.unified_diff(e["before"].splitlines(keepends=True),
                          e["after"].splitlines(keepends=True), fromfile="a/" + e["path"], tofile="b/" + e["path"]))
                                for e in edits)
    # Render only the impact/unchecked list. Never publish the private plan, prior
    # definitions, executor evidence, manifest payloads or arbitrary report extras.
    from acf_runtime.drift import render_impact
    payload["report"] = render_impact(report["impact"])
    if checks is not None:
        payload["report"] += "\n## Fresh seed re-grading\n\n" + "\n".join(
            f"- `{r['seed']}`: {r['status']} — " +
            ("re-grade passed; dependency review pending" if r["category"] == "dependency_review_pending" else r["category"])
            for r in checks["results"]) + "\n"
    if preview and plan.get("source_changes"):
        changes = json.dumps(plan["source_changes"], indent=2, sort_keys=True)
        fence = "`" * max(3, 1 + max((len(m.group()) for m in re.finditer(r"`+", changes)), default=0))
        payload["report"] += "\n## Source changes\n\n" + fence + "json\n" + changes + "\n" + fence + "\n"
    if report.get("unchecked_sources"):
        payload["report"] += "\nUnchecked lineage sources (no verification claimed):\n\n" + "\n".join(
            "- " + repr(source) for source in report["unchecked_sources"]) + "\n"
    output = contained(root, ".nodal/drift-publication", ".nodal")
    atomic_private(output / "publication.json", encoded(payload), overwrite=True)
    atomic_private(output / "status.patch", payload["patch"].encode(), overwrite=True)
    atomic_private(output / "affected.md", payload["report"].encode(), overwrite=True)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--report", default=".nodal/drift-report.json")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--regrade", action="store_true", help="fresh BYO-key shape/entity checks; absent key leaves seeds stale")
    parser.add_argument("--github-output", help="runner-owned GITHUB_OUTPUT file")
    parser.add_argument("--github-summary", help="runner-owned step summary for sanitized status reporting")
    args = parser.parse_args(argv)
    try:
        result = prepare_publication(args.repo_root, args.report, args.base_ref, regrade=args.regrade)
    except (ValueError, OSError, KeyError, TypeError):
        print("drift publication: source changed or invalid proposal; regenerate the drift report", file=sys.stderr)
        return 2
    publish = bool(result["edits"]) or result.get("purpose") != "seed-regrade"
    if args.github_output:
        with Path(args.github_output).open("a") as stream:
            stream.write("publish=" + str(publish).lower() + "\n")
    if args.github_summary:
        with Path(args.github_summary).open("a") as stream:
            stream.write(result["report"])
    print(json.dumps({"status": "prepared_not_published", "batch": result["batch"], "publish": publish,
                      "files": len(result["edits"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
