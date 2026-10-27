#!/usr/bin/env python3
"""Reference live authority over a separate, access-controlled GitHub state ref.

Use an operator-installed absolute path as ACF_GOVERNANCE_COMMAND. gh owns auth.
ACF_GOVERNANCE_REPOSITORY is trusted operator configuration (owner/repo).
State writers run only in protected workflows/environments, never PR jobs.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT if (ROOT / 'acf_runtime').is_dir() else ROOT / 'payload'))
from acf_runtime.governance import append_event, context_files, digest, revision, validate_ledger, timestamp, object_digests, authority_request

REF = "acf-governance"


def api(path, *, method="GET", data=None):
    command = ["gh", "api", "--method", method, path]
    if data is not None:
        command += ["--input", "-"]
    result = subprocess.run(command, input=json.dumps(data) if data is not None else None,
                            capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise ValueError("GitHub authority unavailable; no cached fallback")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def repository():
    value = os.environ.get("ACF_GOVERNANCE_REPOSITORY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("configure trusted ACF_GOVERNANCE_REPOSITORY")
    return value


def state_protection(repo):
    evidence = api(f"repos/{repo}/branches/{REF}/protection")
    restrictions = evidence.get("restrictions") or {}
    writer = os.environ.get("ACF_GOVERNANCE_WRITER")
    allowed = [u["login"] for u in restrictions.get("users", [])] + [a["slug"] for a in restrictions.get("apps", [])]
    if (not writer or allowed != [writer] or restrictions.get("teams") or
            not evidence.get("enforce_admins", {}).get("enabled") or
            evidence.get("allow_force_pushes", {}).get("enabled") or
            evidence.get("allow_deletions", {}).get("enabled")):
        raise ValueError("state ref must restrict writes to the configured authority identity with no force push/deletion")
    return evidence


def read_store(repo):
    state_protection(repo)
    record = api(f"repos/{repo}/contents/state.json?ref={REF}")
    state = json.loads(base64.b64decode(record["content"]))
    validate_ledger(state["events"])
    return state, record["sha"]


def write_store(repo, state, sha):
    # Contents API SHA is compare-and-swap: a concurrent drift block cannot be lost.
    validate_ledger(state["events"])
    api(f"repos/{repo}/contents/state.json", method="PUT", data={
        "message": "Record ACF governance evidence", "branch": REF, "sha": sha,
        "content": base64.b64encode((json.dumps(state, indent=2)+"\n").encode()).decode()})


def protection(repo, branch):
    from urllib.parse import quote
    evidence = api(f"repos/{repo}/branches/{quote(branch, safe='')}/protection")
    reviews = evidence.get("required_pull_request_reviews", {})
    checks = evidence.get("required_status_checks", {})
    required = set(checks.get("contexts", [])) | {c["context"] for c in checks.get("checks", [])}
    if (reviews.get("required_approving_review_count", 0) < 1 or
            not reviews.get("dismiss_stale_reviews") or not reviews.get("require_code_owner_reviews") or
            not evidence.get("enforce_admins", {}).get("enabled") or
            not checks.get("strict") or not {"validate", "approval-policy"}.issubset(required) or
            evidence.get("allow_force_pushes", {}).get("enabled") or
            evidence.get("allow_deletions", {}).get("enabled") or
            reviews.get("bypass_pull_request_allowances", {}).get("users") or
            reviews.get("bypass_pull_request_allowances", {}).get("teams") or
            reviews.get("bypass_pull_request_allowances", {}).get("apps")):
        raise ValueError("approval branch requires enforced human/CODEOWNER review, stale-review dismissal, strict required checks and no bypass/force push")
    return evidence


def approve(repo, branch, sha, content_digest):
    protected = protection(repo, branch)
    pulls = api(f"repos/{repo}/commits/{sha}/pulls?per_page=100")
    candidates = [p for p in pulls if p.get("merged_at") and p.get("merge_commit_sha") == sha and p["base"]["ref"] == branch and p["base"]["repo"]["full_name"] == repo]
    if len(candidates) != 1:
        raise ValueError("revision must identify a reviewed PR merge on the approval branch")
    pr = candidates[0]
    reviews = api(f"repos/{repo}/pulls/{pr['number']}/reviews?per_page=100")
    # Pagination is fail-closed instead of accepting incomplete review history.
    if len(reviews) == 100:
        raise ValueError("review history exceeds supported page; manual authority integration required")
    latest = {}
    for review in reviews:
        if review["state"] != "COMMENTED":
            latest[review["user"]["login"]] = review
    accepted = [r for r in latest.values() if r["state"] == "APPROVED" and r["user"]["type"] == "User"
                and r["user"]["login"] != pr["user"]["login"] and r["commit_id"] == pr["head"]["sha"] and timestamp(r["submitted_at"]) <= timestamp(pr["merged_at"])]
    if len(accepted) < protected["required_pull_request_reviews"]["required_approving_review_count"]:
        raise ValueError("no current human review for merged PR head")
    checks = api(f"repos/{repo}/commits/{pr['head']['sha']}/check-runs?per_page=100")
    if checks.get("total_count", 0) > 100:
        raise ValueError("check history exceeds supported page")
    required = set(protected["required_status_checks"].get("contexts", [])) | {
        c["context"] for c in protected["required_status_checks"].get("checks", [])}
    # Only latest result for each name counts; skipped/neutral is not a pass.
    latest_checks = {}
    for check in sorted(checks["check_runs"], key=lambda c: c["id"]):
        latest_checks[check["name"]] = check
    if any(latest_checks.get(name, {}).get("conclusion") != "success" for name in required):
        raise ValueError("required checks did not pass for reviewed head")
    return dict(revision=sha, branch=branch, content_digest=content_digest,
                review=[{"id": r["id"], "reviewer": r["user"]["login"], "head": r["commit_id"]} for r in accepted],
                checks=[latest_checks[name]["html_url"] for name in sorted(required)],
                protection=digest(protected), pull_request=pr["html_url"])


def repair_checks(repo, urls, sha, block, freshness, content_digest, sources):
    now = datetime.now(timezone.utc)
    if (freshness.get("revision") != sha or freshness.get("content_digest") != content_digest or
            set(sources) - set(freshness.get("sources", {})) or
            not timestamp(freshness["checked_at"]) <= now < timestamp(freshness["expires_at"]) or
            any(v.get("status") != "checked" or not v.get("revision") or not v.get("digest") for v in freshness.get("sources", {}).values())):
        raise ValueError("repair needs current source checks")
    evidence = []
    for url in urls:
        match = re.fullmatch(r"https://github.com/" + re.escape(repo) + r"/actions/runs/([0-9]+)", url)
        if not match:
            raise ValueError("repair check must identify a GitHub Actions run in this repository")
        run = api(f"repos/{repo}/actions/runs/{match.group(1)}")
        if (run.get("head_sha") != sha or run.get("status") != "completed" or
                run.get("conclusion") != "success" or
                timestamp(run["updated_at"]) < timestamp(block["recorded_at"])):
            raise ValueError("repair checks must pass at the repair revision after the source block")
        evidence.append({"url": url, "revision": sha, "updated_at": run["updated_at"], "name": run["name"]})
    return evidence


def serve(repo, request):
    state, _ = read_store(repo)
    branch = state["approval_branch"]
    protection(repo, branch)  # live protection check; a branch name is never proof
    from urllib.parse import quote
    runs = api(f"repos/{repo}/actions/workflows/context-drift.yml/runs?branch={quote(branch, safe='')}&per_page=1").get("workflow_runs", [])
    if (not runs or runs[0].get("status") != "completed" or
            str(runs[0]["id"]) != state.get("last_source_check_run")):
        raise ValueError("latest source check is pending, missing, or failed before publication")
    now = datetime.now(timezone.utc)
    return {"version": 1, "nonce": request["nonce"], "approval_branch": branch,
            "checked_at": now.isoformat(), "expires_at": (now+timedelta(minutes=5)).isoformat(),
            "events": state["events"], "freshness": state.get("freshness", {}).get(request["revision"], {})}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("read", "approve", "drift", "clear", "policy"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--branch", default="main")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--block")
    parser.add_argument("--reason")
    parser.add_argument("--checks", action="append")
    args = parser.parse_args(argv)
    try:
        repo = repository()
        if args.action == "read":
            print(json.dumps(serve(repo, json.load(sys.stdin))))
            return 0
        if args.action == "policy":
            protection(repo, args.branch)
            return 0
        state, store_sha = read_store(repo)
        if state["approval_branch"] != args.branch:
            raise ValueError("authority approval branch mismatch")
        sha = revision(args.root)
        fingerprint = digest(context_files(args.root))
        now = datetime.now(timezone.utc).isoformat()
        events = state["events"]
        if args.action == "approve":
            # Compare committed tree with checkout to reject local edits in evidence.
            from acf_runtime.impact import snapshot
            with snapshot(args.root, sha) as committed:
                if digest(context_files(committed)) != fingerprint:
                    raise ValueError("approval checkout differs from merge revision")
            from acf_runtime.loader import load_context
            registry = load_context(args.root, branch_test=True)
            if registry.errors:
                raise ValueError("approval context does not validate")
            approvals, _ = validate_ledger(events)
            ancestors = []
            for prior in approvals:
                result = subprocess.run(["git", "-C", str(args.root), "merge-base", "--is-ancestor", prior, sha],
                                        capture_output=True, check=False)
                if result.returncode == 0:
                    ancestors.append(prior)
                elif result.returncode != 1:
                    raise ValueError("approval ancestry unavailable; fetch full history")
            events = append_event(events, "approve", **approve(repo, args.branch, sha, fingerprint), recorded_at=now,
                                  ancestors=ancestors, object_digests=object_digests(registry))
        elif args.action == "drift":
            if not args.report:
                raise ValueError("drift requires a checked report")
            report = json.loads(args.report.read_text())
            targets = [item["id"] for item in report["impact"]["objects"]]
            if report.get("unchecked_sources"):
                targets = ["*"]
            evidence = {"report_digest": digest(report), "revision": sha,
                        "source_changes": report.get("changes", []), "unchecked": report.get("unchecked_sources", [])}
            if targets:
                events = append_event(events, "block", targets=targets, reason="source drift or unavailable source check",
                                      source_evidence=evidence, revision=sha, recorded_at=now)
            # Never infer currency from a successful exit without actual source evidence.
            state["last_source_check_run"] = os.environ.get("GITHUB_RUN_ID")
            source_checks = report.get("source_evidence", {})
            state.setdefault("freshness", {})[sha] = {"revision": sha, "content_digest": fingerprint,
                "checked_at": now, "expires_at": (datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),
                "sources": source_checks}
        else:
            # Protected environment human approval is required for this workflow.
            approval = approve(repo, args.branch, sha, fingerprint)
            approvals, blocks = validate_ledger(events)
            if sha not in approvals or not args.checks or not args.reason or args.block not in blocks:
                raise ValueError("clear requires recorded merge approval, block, repair reason and fresh check evidence")
            if approvals[sha]["content_digest"] != fingerprint:
                raise ValueError("repair revision changed")
            from acf_runtime.loader import load_context
            registry = load_context(args.root, branch_test=True)
            if registry.errors or any(n.blocking_reasons for n in registry.nodes.values()):
                raise ValueError("repair context has unresolved blockers")
            sources = authority_request(registry)["sources"]
            checks = repair_checks(repo, args.checks, sha, blocks[args.block], state.get("freshness", {}).get(sha, {}), fingerprint, sources)
            events = append_event(events, "clear", block=args.block, revision=sha, reason=args.reason,
                checks=checks, source_evidence=blocks[args.block]["source_evidence"],
                review=approval["review"], recorded_at=now)
        state["events"] = events
        write_store(repo, state, store_sha)
        print(json.dumps({"status": "recorded", "kind": args.action, "revision": sha}))
        return 0
    except (ValueError, KeyError, OSError, TypeError, subprocess.SubprocessError):
        print("governance: authority/evidence unavailable or invalid; governed use remains blocked", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
