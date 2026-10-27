"""Live approval/freshness authority boundary, independent of authored context.

The command is operator configuration, never read from context.config.yaml. It
must read the authoritative store on every request (no offline/cache fallback).
No credentials, shell evaluation, or repository-supplied executable is involved.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def context_files(root):
    """Bind all governed prose, definitions, shared fragments and configuration."""
    root = Path(root)
    paths = [root / "context.config.yaml"]
    for name in ("company", "domains", "entities", "methods", "evals/seeds"):
        paths.extend(p for p in (root / name).rglob("*") if p.is_file())
    result = {}
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("governed content cannot escape the context root")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def revision(root):
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("authority timestamps require a timezone")
    return dt


def object_digests(registry):
    """Bind clearance to affected definitions, their dependencies and shared prose."""
    files = context_files(registry.root)
    result = {}
    for node in registry.nodes.values():
        pending, members = [node.id], {}
        domains = set()
        while pending:
            key = pending.pop()
            if key in members or key not in registry.nodes:
                continue
            member = registry.nodes[key]
            members[key] = {"data": member.data, "body": member.body, "lineage": sorted(member.lineage)}
            domains.add(member.domain)
            if member.domain:
                pending.append("domain:" + member.domain)
            pending.extend(member.dependencies)
        prose = {path: value for path, value in files.items() if path.startswith("company/") or
                 any(path.startswith(f"domains/{domain}/") and path.endswith(".md") for domain in domains if domain)}
        # Configuration changes are conservative; a new source/calendar can
        # change the meaning even when the authored object remains identical.
        result[node.id] = digest({"members": members, "prose": prose, "config": registry.config})
    return result


def clearance_scope(approval, block):
    objects = approval.get("object_digests", {})
    targets = block["targets"]
    if "*" in targets or any(target not in objects for target in targets):
        return approval["content_digest"]
    return digest({target: objects[target] for target in sorted(targets)})


def validate_ledger(events):
    """Append-only hash chain. Clears name a block and reviewed repair evidence."""
    previous, blocks, approvals = None, {}, {}
    for event in events:
        body = {k: v for k, v in event.items() if k != "id"}
        if event.get("previous") != previous or event.get("id") != digest(body):
            raise ValueError("invalid governance history")
        previous = event["id"]
        kind = event["kind"]
        if kind == "approve":
            if not (event.get("revision") and event.get("content_digest") and
                    event.get("review") and event.get("checks") and event.get("protection")):
                raise ValueError("approval requires revision, human review, checks and protection evidence")
            approvals[event["revision"]] = event
            for block in blocks.values():
                scope = clearance_scope(event, block)
                if any(parent in event.get("ancestors", []) and scope == old_scope
                       for parent, old_scope in block["clearances"].items()):
                    block["cleared_revisions"].append(event["revision"])
                    block["clearances"][event["revision"]] = scope
        elif kind == "block":
            if not event.get("reason") or not event.get("source_evidence") or not event.get("targets"):
                raise ValueError("block requires targets, reason and source evidence")
            blocks[event["id"]] = {**event, "cleared_revisions": [], "clearances": {}}
        elif kind == "clear":
            block = blocks.get(event.get("block"))
            approval = approvals.get(event.get("revision"))
            if not block or not approval or not event.get("reason") or not event.get("checks"):
                raise ValueError("clear requires an active block, reviewed revision and passing checks")
            if event.get("source_evidence") != block["source_evidence"]:
                raise ValueError("repair must address the blocked source evidence")
            if event["revision"] in block["cleared_revisions"]:
                raise ValueError("duplicate clearance")
            block["cleared_revisions"].append(event["revision"])
            block["clearances"][event["revision"]] = clearance_scope(approval, block)
        else:
            raise ValueError("unknown governance event")
    return approvals, blocks


def append_event(events, kind, **fields):
    validate_ledger(events)
    event = {"kind": kind, "previous": events[-1]["id"] if events else None, **fields}
    event["id"] = digest(event)
    result = [*events, event]
    validate_ledger(result)
    return result


def authority_request(registry):
    files = context_files(registry.root)
    sources = {source for n in registry.nodes.values() for source, _ in n.lineage}
    for domain in registry.config.get("domains", {}).values():
        sources.update(source for source, _ in registry._lineage((domain or {}).get("lineage")))
    return {"version": 1, "nonce": uuid.uuid4().hex, "revision": revision(registry.root),
            "content_digest": digest(files), "approval_branch": registry.config.get("approval_branch", "main"),
            "sources": sorted(sources)}


def read_authority(request):
    raw = os.environ.get("ACF_GOVERNANCE_COMMAND")
    if not raw:
        raise ValueError("authority_unconfigured")
    command = json.loads(raw)
    if (not isinstance(command, list) or not command or
            not all(isinstance(v, str) and v for v in command) or not Path(command[0]).is_absolute()):
        raise ValueError("authority_command_must_be_absolute_argv")
    result = subprocess.run(command, input=json.dumps(request), capture_output=True,
                            text=True, timeout=30, check=False)
    if result.returncode:
        raise ValueError("authority_unavailable")
    return json.loads(result.stdout)


def apply_governance(registry, *, branch_test=False, authority=None):
    """Fail closed. branch_test is caller intent; never a repo-authored setting."""
    registry.governance = {"mode": "branch-test" if branch_test else "governed", "approved": False}
    if branch_test:
        registry.governance["reason"] = "proposed_context_test_only"
        for node in registry.nodes.values():
            node.approval_state = "proposed"
        return
    try:
        request = authority_request(registry)
        response = (authority or read_authority)(request)
        now = datetime.now(timezone.utc)
        if (response.get("nonce") != request["nonce"] or response.get("version") != 1 or
                response.get("approval_branch") != request["approval_branch"] or
                not timestamp(response["checked_at"]) <= now < timestamp(response["expires_at"]) or
                (now - timestamp(response["checked_at"])).total_seconds() > 300):
            raise ValueError("authority_missing_or_expired")
        approvals, blocks = validate_ledger(response["events"])
        approval = approvals.get(request["revision"])
        if not approval or approval["content_digest"] != request["content_digest"]:
            raise ValueError("revision_not_approved")
        if approval.get("branch") != request["approval_branch"]:
            raise ValueError("wrong_approval_branch")
        registry.governance.update(approved=True, revision=request["revision"],
                                   content_digest=request["content_digest"], approval=approval["id"])
        freshness = response["freshness"]
        if freshness.get("revision") != request["revision"] or freshness.get("content_digest") != request["content_digest"]:
            raise ValueError("freshness_revision_mismatch")
        if not timestamp(freshness["checked_at"]) <= now < timestamp(freshness["expires_at"]):
            raise ValueError("freshness_missing_or_expired")
        for source in request["sources"]:
            evidence = freshness.get("sources", {}).get(source, {})
            if evidence.get("status") != "checked" or not evidence.get("revision") or not evidence.get("digest"):
                raise ValueError("source_freshness_unavailable:" + source)
        registry.governance.update(approved=True, revision=request["revision"],
            content_digest=request["content_digest"], approval=approval["id"],
            checked_at=response["checked_at"], expires_at=response["expires_at"],
            history_head=response["events"][-1]["id"], freshness=freshness)
        registry.governance["freshness_state"] = "current"
        for node in registry.nodes.values():
            node.approval_state = "approved"
            for identifier, block in blocks.items():
                if request["revision"] not in block["cleared_revisions"] and ("*" in block["targets"] or node.id in block["targets"]):
                    node.local_blockers.add("stale:" + identifier)
                    registry.governance["freshness_state"] = "stale"
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError, subprocess.SubprocessError):
        registry.governance["reason"] = "approval_or_freshness_unavailable"
        registry.governance["freshness_state"] = "unavailable"
        for node in registry.nodes.values():
            node.approval_state = "approved" if registry.governance["approved"] else "unavailable"
            node.local_blockers.add("governance:approval_or_freshness_unavailable")


def blocked_prose_domains(registry):
    """Unstructured prose cannot be split reliably around a blocked definition."""
    return {n.domain for n in registry.nodes.values() if n.domain and n.blocking_reasons and n.kind != "evalseed"}


def eligible_domains(registry):
    domains = set(registry.domains)
    for domain in list(domains):
        owner = registry.nodes.get("domain:" + domain)
        definitions = [n for n in registry.nodes.values() if n.domain == domain and n.kind in ("metric", "method", "entity")]
        if (owner and owner.blocking_reasons) or (definitions and all(n.blocking_reasons for n in definitions)):
            domains.discard(domain)
    return domains


def require_working_branch(root, branch="main"):
    result = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD"],
                            capture_output=True, text=True, check=False)
    if result.returncode or result.stdout.strip() == branch:
        raise ValueError("author context on a named working branch, not the approval branch")
