"""Explicit, resumable local review transactions for observed demand.

Preparation writes only private proposals. Application is a human review
attestation, uses revision checks and a write-ahead journal, and never confirms
new definitions. Cooperating queue writers must take the same advisory lock.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import tempfile
import uuid

import yaml

from .loader import Schemas, discover_docs, load_context
from .observed import pending_first, read_queue, retain_variant
from .verified import atomic_private, contained
from eval_harness.execution import strict_json
from .matching import match_registry

QUEUE = "evals/observed/queue.jsonl"
LOCAL = ".nodal/observed"


def fingerprint(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def schema_dir(root):
    path = root / "schemas"
    return path if path.is_dir() else Path(__file__).resolve().parents[1] / "schemas"


def schema_hash(root):
    return fingerprint(encode({p.name: fingerprint(p.read_bytes())
                              for p in sorted(schema_dir(root).glob("*.json"))}))


def documents(root):
    paths = {p.relative_to(root).as_posix() for p, _ in discover_docs(root)}
    paths.update(p.relative_to(root).as_posix() for pattern in
                 ("domains/*/*.md", "company/*.md") for p in root.glob(pattern))
    return {name: contained(root, name, ".").read_bytes() for name in sorted(paths)}


@contextmanager
def locked(root):
    path = contained(root, LOCAL + "/review.lock", LOCAL)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+") as stream:
        path.chmod(0o600)
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another observed review is active") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def inputs(root):
    registry = load_context(root)
    if registry.errors:
        raise ValueError("context must validate before observed review")
    rows = read_queue(root, Schemas(schema_dir(root)), registry)
    return registry, rows or []


def unfinished(root, allowed=None):
    directory = contained(root, LOCAL + "/history", LOCAL)
    for path in directory.glob("*.json"):
        path = contained(root, path.relative_to(root).as_posix(), LOCAL)
        record = strict_json(path.read_text())
        if record.get("state") != "complete" and path.stem != allowed:
            raise ValueError("resume the incomplete observed transaction before preparing or applying another")


def list_pending(root):
    root = Path(root).resolve()
    _, rows = inputs(root)
    return pending_first(rows)


def observation(rows, identifier):
    found = next((r for r in rows if r["id"] == identifier), None)
    if found is None or found["status"] != "pending":
        raise ValueError("observation must exist and be pending")
    return found


def editable(name):
    # No arbitrary files, support tooling, shared fragments or inferred prose edits.
    return bool(re.fullmatch(
        r"(?:domains/[A-Za-z0-9_-]+/metrics/[A-Za-z0-9][A-Za-z0-9_-]*\.yaml|"
        r"methods/[A-Za-z0-9][A-Za-z0-9_-]*\.md|"
        r"evals/seeds/[A-Za-z0-9][A-Za-z0-9_.-]*\.seed\.yaml)", name))


def validate_changes(root, contents, changes, *, variant_path=None):
    """Validate the entire proposed graph without writing authored context."""
    if not isinstance(changes, list) or not all(isinstance(c, dict) and
            set(c) == {"path", "content"} and isinstance(c["path"], str) and
            isinstance(c["content"], str) for c in changes):
        raise ValueError("changes must contain only path and UTF-8 content")
    if len({c["path"] for c in changes}) != len(changes):
        raise ValueError("duplicate destination")
    for change in changes:
        if not editable(change["path"]):
            raise ValueError("destination must be a per-metric, method or seed artifact")
        contained(root, change["path"], ".")
    with tempfile.TemporaryDirectory(prefix="nodal-observed-preview-") as directory:
        staged = Path(directory)
        for name, raw in {**contents, **{c["path"]: c["content"].encode() for c in changes}}.items():
            destination = staged / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        registry = load_context(staged, schemas=schema_dir(root))
        if registry.errors:
            codes = sorted({e.code for e in registry.errors})
            raise ValueError("proposed context does not validate: " + ", ".join(codes))
        for change in changes:
            nodes = [n for n in registry.nodes.values() if n.path == change["path"]]
            if not nodes:
                raise ValueError("destination must be a loaded ACF artifact")
            if change["path"] != variant_path:
                if any(n.data.get("status") not in (None, "draft") for n in nodes):
                    raise ValueError("review edits must remain draft; confirm separately after review")
                # Prior attribution may remain on edited drafts, but cannot be invented.
                original = load_context(root).nodes
                for node in nodes:
                    previous = original.get(node.id)
                    for key in ("approver", "confirmed_at"):
                        if key in node.data and (previous is None or
                                node.data[key] != previous.data.get(key)):
                            raise ValueError("draft review cannot create or change confirmation metadata")
        return registry


def draft_status(registry, changes):
    if not changes:
        return "declined"
    paths = {c["path"] for c in changes}
    seeds = [s for s in registry.seeds if s.path in paths]
    return "declined" if seeds and all(s.data["expected"]["kind"] == "negative" for s in seeds) else "promoted"


def prepare(root, identifier, *, reviewer, changes=(), disposition="drafted", variant=None,
            reviewed_ir=None, domain=None):
    """Create an immutable preview. `variant` is {seed, ir}; no text rewriting."""
    root = Path(root).resolve()
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("reviewer is required")
    if not isinstance(disposition, str) or not disposition.strip():
        raise ValueError("disposition is required")
    with locked(root):
        unfinished(root)
        registry, rows = inputs(root)
        row = observation(rows, identifier)
        contents = documents(root)
        selected_domain = domain or row.get("domain")
        overflow, variant_path = [], None
        changes = list(changes)
        if variant is not None:
            if changes:
                raise ValueError("variant and draft edits are separate review operations")
            node = registry.nodes.get(variant["seed"])
            if node is None or node.kind != "evalseed":
                raise ValueError("variant target must be a seed ID")
            if row.get("domain") and row["domain"] != node.domain:
                raise ValueError("variant must belong to the observation domain")
            match = match_registry(registry, variant["ir"], node.domain)
            if match["relation"] in ("unresolved", "ambiguous", "decomposes"):
                raise ValueError("reviewed IR must resolve one interpretation; retain unresolved questions as pending")
            if (match["relation"] != "equivalent" or node.id not in match.get("seeds", [])
                    or match.get("blockers")):
                raise ValueError("variant requires reviewed equivalent IR and eligible, nonconflicting seeds")
            value = {"text": row["text"], "observed_at": row["asked_at"],
                     "provenance": "observed", "approver": reviewer}
            updated, disposition, overflow = retain_variant(node.data, value,
                maximum=registry.config.get("variants", {}).get("max_per_seed", 20))
            variant_path = node.path
            selected_domain, reviewed_ir = node.domain, variant["ir"]
            changes = [{"path": node.path, "content": yaml.safe_dump(updated, sort_keys=False,
                                                                       allow_unicode=True)}]
            status = "linked"
        proposed_registry = validate_changes(root, contents, changes, variant_path=variant_path)
        if variant is None:
            status = draft_status(proposed_registry, changes)
        resolution = None
        if reviewed_ir is not None:
            if selected_domain not in proposed_registry.domains:
                raise ValueError("reviewed IR requires a known domain")
            resolved = match_registry(proposed_registry, reviewed_ir, selected_domain)
            if resolved["relation"] in ("unresolved", "ambiguous", "decomposes"):
                raise ValueError("reviewed IR must resolve one interpretation; retain unresolved questions as pending")
            resolution = {"domain": selected_domain, "ir": resolved["ir"],
                          "relation": resolved["relation"], "nearest_seeds": resolved["seeds"]}
        identifier = str(uuid.uuid4())
        plan = {"version": 1, "id": identifier, "reviewer": reviewer,
                "observation": row, "status": status, "disposition": disposition,
                "variant": variant, "variant_path": variant_path, "overflow": overflow,
                "resolution": resolution,
                "context": {p: fingerprint(raw) for p, raw in contents.items()},
                "schemas": schema_hash(root), "changes": changes,
                "created_at": datetime.now(timezone.utc).isoformat()}
        path = contained(root, f"{LOCAL}/proposals/{identifier}.json", LOCAL)
        atomic_private(path, encode(plan))
        return {"proposal": path.relative_to(root).as_posix(), "sha256": fingerprint(encode(plan)),
                "status": "awaiting_review", "destinations": [c["path"] for c in changes],
                "disposition": disposition, "overflow_count": len(overflow)}


def _revisions(root, plan):
    current = {p: fingerprint(raw) for p, raw in documents(root).items()}
    original = plan["context"]
    proposed = {c["path"]: fingerprint(c["content"].encode()) for c in plan["changes"]}
    if set(current) - set(original) - set(proposed) or set(original) - set(current):
        raise ValueError("context paths changed after review; resolve before resuming")
    for name in set(current) | set(proposed):
        if current.get(name) not in {original.get(name), proposed.get(name)}:
            raise ValueError("context changed after review; resolve before resuming")
    if schema_hash(root) != plan["schemas"]:
        raise ValueError("schemas changed after review")


def _resolution(plan, registry):
    from .matching import match_registry
    resolution = plan.get("resolution")
    if not resolution:
        if plan["variant"] is not None:
            raise ValueError("variant requires its reviewed resolution")
        return
    if not isinstance(resolution, dict) or set(resolution) != {"domain", "ir", "relation", "nearest_seeds"}:
        raise ValueError("invalid reviewed resolution")
    ir = plan["variant"]["ir"] if plan["variant"] else resolution["ir"]
    result = match_registry(registry, ir, resolution["domain"])
    if result["relation"] in ("unresolved", "ambiguous", "decomposes") or resolution != {
            "domain": resolution["domain"], "ir": result["ir"], "relation": result["relation"],
            "nearest_seeds": result["seeds"]}:
        raise ValueError("reviewed resolution no longer matches the proposed context")


def apply(root, proposal, *, reviewer, sha256):
    """Apply exactly the reviewed digest, or resume that same journal idempotently.

    Full before/after artifacts and displaced variants remain in the private
    journal. A concurrent edit stops recovery; it is never overwritten.
    """
    root = Path(root).resolve()
    with locked(root):
        path = contained(root, proposal, LOCAL + "/proposals")
        raw = path.read_bytes()
        if fingerprint(raw) != sha256:
            raise ValueError("proposal digest changed; review the current preview")
        plan = strict_json(raw.decode())
        if plan["version"] != 1 or str(uuid.UUID(plan["id"])) != path.stem:
            raise ValueError("invalid proposal identifier/version")
        if not reviewer.strip() or plan["reviewer"] != reviewer:
            raise ValueError("reviewer must match the reviewed proposal")
        unfinished(root, plan["id"])
        journal_path = contained(root, f"{LOCAL}/history/{plan['id']}.json", LOCAL)
        if journal_path.exists():
            journal = strict_json(journal_path.read_text())
            if (journal["sha256"] != sha256 or journal["reviewer"] != reviewer
                    or journal["plan"] != plan):
                raise ValueError("journal does not match the reviewed proposal")
            if journal["state"] == "complete":
                return {"status": "complete", "id": plan["id"], "resumed": True}
        else:
            registry, rows = inputs(root)
            if observation(rows, plan["observation"]["id"]) != plan["observation"]:
                raise ValueError("observation changed; prepare and review again")
            current = documents(root)
            if {p: fingerprint(v) for p, v in current.items()} != plan["context"]:
                raise ValueError("context changed; prepare and review again")
            if schema_hash(root) != plan["schemas"]:
                raise ValueError("schemas changed; prepare and review again")
            # Proposals are untrusted data: recheck paths and drafting constraints.
            proposed_registry = validate_changes(root, current, plan["changes"], variant_path=plan["variant_path"])
            _resolution(plan, proposed_registry)
            if plan["variant"] is not None:
                node = registry.nodes.get(plan["variant"]["seed"])
                if not node or node.path != plan["variant_path"]:
                    raise ValueError("invalid variant target")
                match = match_registry(registry, plan["variant"]["ir"], node.domain)
                expected, outcome, overflow = retain_variant(node.data, {
                    "text": plan["observation"]["text"], "observed_at": plan["observation"]["asked_at"],
                    "provenance": "observed", "approver": reviewer},
                    maximum=registry.config.get("variants", {}).get("max_per_seed", 20))
                exact = [{"path": node.path, "content": yaml.safe_dump(expected, sort_keys=False,
                                                                         allow_unicode=True)}]
                if (match["relation"] != "equivalent" or match.get("blockers") or
                        node.id not in match.get("seeds", []) or plan["changes"] != exact or
                        plan["overflow"] != overflow or plan["disposition"] != outcome or
                        plan["status"] != "linked"):
                    raise ValueError("variant proposal no longer matches reviewed insertion")
            elif plan["variant_path"] is not None or plan["status"] != draft_status(proposed_registry, plan["changes"]):
                raise ValueError("invalid draft/dismissal disposition")
            journal = {"version": 1, "sha256": sha256, "reviewer": reviewer,
                       "state": "applying", "plan": plan,
                       "before": {c["path"]: current[c["path"]].decode() if c["path"] in current else None
                                  for c in plan["changes"]},
                       "reviewed_at": datetime.now(timezone.utc).isoformat()}
            atomic_private(journal_path, encode(journal))
        _revisions(root, plan)
        proposed_registry = validate_changes(root, documents(root), plan["changes"], variant_path=plan["variant_path"])
        _resolution(plan, proposed_registry)
        for change in plan["changes"]:
            destination = contained(root, change["path"], ".")
            actual = fingerprint(destination.read_bytes()) if destination.exists() else None
            target = change["content"].encode()
            if actual == fingerprint(target):
                continue
            if actual != plan["context"].get(change["path"]):
                raise ValueError("destination changed during apply; preserve it and resolve before resuming")
            atomic_private(destination, target, overwrite=destination.exists())
        queue_path = contained(root, QUEUE, "evals/observed")
        queue_raw = queue_path.read_bytes()
        rows = read_queue(root, Schemas(schema_dir(root)))
        updated = deepcopy(plan["observation"])
        updated.update(status=plan["status"], disposition=plan["disposition"],
                       destinations=[c["path"] for c in plan["changes"]])
        if plan.get("resolution"):
            updated.update(plan["resolution"])
            updated.pop("metric_candidates", None)
        if Schemas(schema_dir(root)).errors("observed", updated):
            raise ValueError("invalid reviewed queue disposition")
        found = False
        for index, row in enumerate(rows or []):
            if row["id"] == updated["id"]:
                if row not in (plan["observation"], updated):
                    raise ValueError("observation changed during apply; resolve before resuming")
                rows[index], found = updated, True
        if not found:
            raise ValueError("observation removed during apply")
        if queue_path.read_bytes() != queue_raw:
            raise ValueError("queue changed during apply; resume with its writer stopped")
        atomic_private(queue_path, ("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)).encode(),
                       overwrite=True)
        journal.update(state="complete", completed_at=datetime.now(timezone.utc).isoformat())
        atomic_private(journal_path, encode(journal), overwrite=True)
        return {"status": "complete", "id": plan["id"], "disposition": plan["disposition"],
                "destinations": updated["destinations"], "history": journal_path.relative_to(root).as_posix()}
