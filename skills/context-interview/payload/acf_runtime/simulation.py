"""Local simulated-interview marker, transcript and human-review receipts.

This module never opens the knowledge brief or calls an agent. Only the isolated
responder reads the brief. Receipts record explicit operator attestations; they
are not proof that a person, warehouse or notebook performed an action.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re

from .loader import load_context
from .verified import atomic_private
from eval_harness.execution import strict_json

MARKER = ".sim-analyst.json"


def _bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _path(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError("simulation paths must be absolute")
    path = Path(value)
    if ".." in path.parts:
        raise ValueError("simulation paths cannot contain traversal")
    for parent in (path, *path.parents):
        if parent.is_symlink():
            # macOS /var and /tmp are standard aliases; callers use resolved paths.
            raise ValueError("simulation paths cannot contain symlinks; use resolved paths")
    return path


def load_marker(path):
    path = _path(str(Path(path).absolute()))
    data = strict_json(path.read_text())
    if not isinstance(data, dict) or set(data) - {"responses", "log", "state", "mode", "run_id"}:
        raise ValueError("invalid simulation marker fields")
    responses, log = _path(data.get("responses")), _path(data.get("log"))
    state = _path(data.get("state", str(log.with_suffix(".state.json"))))
    if not responses.is_file():
        raise ValueError("simulation brief is missing")
    if responses.is_relative_to(path.parent):
        raise ValueError("simulation brief must remain outside the interviewer project")
    if log.parent != responses.parent or state.parent != log.parent:
        raise ValueError("simulation log/state must be siblings of the private brief")
    if len({responses, log, state, path}) != 4:
        raise ValueError("simulation brief, log, state and marker must be distinct files")
    mode = data.get("mode", "interactive")
    if mode not in ("interactive", "non-interactive"):
        raise ValueError("invalid simulation mode")
    if "run_id" in data and (not isinstance(data["run_id"], str) or not data["run_id"].strip()):
        raise ValueError("invalid simulation run ID")
    return {**data, "state": str(state), "mode": mode}


def handoff(marker, target):
    """Copy only marker pointers; never copy/read the brief into the context repo."""
    data = load_marker(marker)
    target = Path(target).resolve()
    if Path(data["responses"]).is_relative_to(target):
        raise ValueError("target would contain the private brief")
    destination = target / MARKER
    if destination.exists() and load_marker(destination) != data:
        raise ValueError("target already has a different simulation marker")
    atomic_private(destination, _bytes(data), overwrite=destination.exists())
    return destination


@contextmanager
def _state(marker):
    data = load_marker(marker)
    path = Path(data["state"])
    lock = _path(str(path.with_suffix(path.suffix + ".lock")))
    with lock.open("a+") as stream:
        lock.chmod(0o600)
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("simulation state is in use; retry after the active write") from None
        try:
            if path.exists():
                state = strict_json(path.read_text())
                if not isinstance(state, dict) or state.get("version") != 1:
                    raise ValueError("unsupported simulation state")
                if state.get("responses") != data["responses"] or state.get("run_id") != data.get("run_id"):
                    raise ValueError("simulation state belongs to a different run")
            else:
                log = Path(data["log"])
                state = {"version": 1, "responses": data["responses"], "run_id": data.get("run_id"),
                         "events": [], "questions": {}, "confirmations": [],
                         "preamble": log.read_text() if log.exists() else ""}
            yield data, state
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _save(data, state):
    path = Path(data["state"])
    atomic_private(path, _bytes(state), overwrite=path.exists())
    # State is authoritative. Re-rendering repairs a crash between state/log writes.
    lines = [state["preamble"], "# Simulated analyst transcript", "",
             "Simulated answers are draft input, not human confirmations or execution evidence.", ""]
    for event in state["events"]:
        lines.extend([f"## {event['id']} — Stage {event['stage']}",
                      f"{event['at']} | {event['source']} | {event['outcome']}", "",
                      "Question:", event["question"], "", "Reply:", event["reply"], ""])
        if event.get("reviewer"):
            lines.extend(["Human respondent: " + event["reviewer"], ""])
    for receipt in state["confirmations"]:
        lines.extend([f"Human confirmation: {receipt['object']} by {receipt['reviewer']} "
                      f"at {receipt['at']} (sha256 {receipt['sha256']})", ""])
    log = Path(data["log"])
    atomic_private(log, ("\n".join(lines).rstrip() + "\n").encode(), overwrite=log.exists())


def record(marker, *, identifier, stage, question, reply, source="simulated", reviewer=None):
    if not all(isinstance(v, str) and v.strip() for v in (identifier, stage, question, reply)):
        raise ValueError("question ID, stage, question and reply must be nonempty strings")
    if source not in ("simulated", "human"):
        raise ValueError("source must be simulated or human")
    if source == "human" and (not isinstance(reviewer, str) or not reviewer.strip()):
        raise ValueError("a human reply requires the actual respondent's name")
    if source == "simulated" and reviewer:
        raise ValueError("a simulated reply cannot name a human reviewer")
    with _state(marker) as (data, state):
        if source == "human":
            outcome = "answered_by_human"
        elif (reply.startswith("CONFIDENT:") and reply.removeprefix("CONFIDENT:").strip()
              and not re.search(r"\bNOT_CONFIDENT\s*:", reply, re.IGNORECASE)):
            outcome = "answered_simulated"
        else:
            outcome = "pending_human"
        existing = state["questions"].get(identifier)
        event = {"id": identifier, "stage": stage, "question": question, "reply": reply,
                 "source": source, "reviewer": reviewer, "outcome": outcome}
        if existing:
            if any(existing[k] != event[k] for k in ("stage", "question")):
                raise ValueError("question ID already belongs to a different question")
            if all(existing[k] == v for k, v in event.items()):
                _save(data, state)
                return _result(data, existing)
            if existing["outcome"] != "pending_human":
                raise ValueError("answered question changed; use a new question ID for a new interpretation")
            if source != "human":
                raise ValueError("pending question requires the actual human reply, not a second simulated guess")
        event["at"] = datetime.now(timezone.utc).isoformat()
        state["events"].append(event)
        state["questions"][identifier] = event
        _save(data, state)
        return _result(data, event)


def _result(data, event):
    pending = event["outcome"] == "pending_human"
    return {"id": event["id"], "outcome": event["outcome"],
            "next": ("pause" if data["mode"] == "non-interactive" else "ask_human") if pending else "continue_drafting"}


def pending(marker):
    with _state(marker) as (data, state):
        _save(data, state)
        return [event for event in state["questions"].values() if event["outcome"] == "pending_human"]


def summarize(root, marker):
    """Draft-capture deliverable, never an attestation of live verification."""
    root = Path(root).resolve()
    with _state(marker) as (data, state):
        waiting = [{key: event[key] for key in ("id", "stage", "question")}
                   for event in state["questions"].values() if event["outcome"] == "pending_human"]
        result = {"context_repo": str(root), "exchange_log": data["log"],
                  "context_created": (root / "context.config.yaml").is_file(),
                  "pending_human_questions": waiting, "draft_metrics": [], "draft_methods": [],
                  "open_decisions": [], "verification_work": [], "validation_errors": [],
                  "execution_verification": "not_established_by_simulation"}
    if not result["context_created"]:
        result["context_valid"] = False
        return result
    registry = load_context(root)
    result["validation_errors"] = [str(d) for d in registry.errors]
    result["context_valid"] = not registry.errors
    for node in registry.metrics + registry.methods:
        if node.approval_state != "approved" or node.blocking_reasons:
            result["draft_metrics" if node.kind == "metric" else "draft_methods"].append(node.path)
        for decision in node.data.get("open_decisions", []):
            result["open_decisions"].append({"object": node.id, **decision})
        if node.kind == "method":
            result["verification_work"].append({"object": node.id, "next":
                "review_method_then_select_real_verification_case" if node.approval_state != "approved" or node.blocking_reasons
                else "select_case_and_inspect_real_execution_evidence"})
    for seed in registry.seeds:
        if seed.data["expected"]["kind"] == "value_at_snapshot" and (seed.approval_state != "approved" or seed.blocking_reasons):
            result["verification_work"].append({"object": seed.id, "next": "independent_execution_and_human_review"})
    return result


def attest_confirmation(marker, root, identifier, reviewer):
    """Record an explicit actual-human approval of already-reviewed authored bytes.

    Does not change status, approval fields, results or definitions. Never invoke
    this based on a simulated response; the caller must have actual human approval.
    """
    root = Path(root).resolve()
    registry = load_context(root)
    if registry.errors:
        raise ValueError("context must validate before recording human confirmation")
    node = registry.nodes.get(identifier)
    if node is None:
        raise ValueError("confirmation target must be a context object")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("actual human reviewer required")
    if node.data.get("approver") and node.data["approver"] != reviewer:
        raise ValueError("reviewer must match the object's actual human approver")
    path = root / node.path
    with _state(marker) as (data, state):
        receipt = {"root": str(root), "object": identifier, "path": node.path,
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "reviewer": reviewer,
                   "confirmed_at": node.data.get("confirmed_at")}
        if not any(all(r.get(k) == v for k, v in receipt.items()) for r in state["confirmations"]):
            receipt["at"] = datetime.now(timezone.utc).isoformat()
            state["confirmations"].append(receipt)
        _save(data, state)
        return {"object": identifier, "status": "human_attestation_recorded"}


def check_output(root, marker=None, *, require_content=False):
    """Return problems; a simulator cannot supply confirmed output by itself."""
    root = Path(root).resolve()
    marker = Path(marker) if marker else root / MARKER
    data = load_marker(marker)
    if not (root / MARKER).is_file() or load_marker(root / MARKER) != data:
        return ["simulation marker was not handed off to the generated context repo"]
    registry = load_context(root)
    problems = [str(e) for e in registry.errors]
    state_path = Path(data["state"])
    state = strict_json(state_path.read_text()) if state_path.exists() else {"confirmations": [], "questions": {}}
    if state_path.exists() and (state.get("responses") != data["responses"] or state.get("run_id") != data.get("run_id")):
        return ["simulation state belongs to a different run"]
    for node in registry.nodes.values():
        receipts = [r for r in state["confirmations"] if r["root"] == str(root) and r["object"] == node.id]
        if node.approval_state == "approved" or node.data.get("status") == "confirmed":
            digest = hashlib.sha256((root / node.path).read_bytes()).hexdigest()
            if not any(r["sha256"] == digest and (node.kind not in ("metric", "method", "evalseed") or
                       (not node.data.get("approver") or r["reviewer"] == node.data["approver"])) for r in receipts):
                problems.append(f"simulator cannot confirm {node.id}; explicit matching human receipt is missing")
        elif any(node.data.get(k) for k in ("approver", "confirmed_at")):
            if not any(r["reviewer"] == node.data.get("approver") and
                       r.get("confirmed_at") == node.data.get("confirmed_at") for r in receipts):
                problems.append(f"simulated draft {node.id} contains unsubstantiated confirmation metadata")
    if require_content:
        if not registry.metrics or not registry.seeds:
            problems.append("simulated interview did not produce a metric and an eval seed")
        if not state["questions"]:
            problems.append("simulated interview has no logged question/answer exchange")
    return problems
