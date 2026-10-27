"""Explicit customer executor protocol. No shell, credentials or implicit runs.

Executors are trusted customer programs, not model-generated commands. A receipt
is their attestation, not an OS sandbox or independent proof of execution.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import uuid


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("non-finite JSON number")
    return json.loads(text, object_pairs_hook=unique, parse_constant=constant)


def private_json(path, value):
    raw = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(raw)


def validate_command(command):
    if command is not None and (not isinstance(command, list) or not command or
                               not all(isinstance(x, str) and x for x in command)):
        raise ValueError("executor command must be a nonempty JSON argv array")


def invoke(command, payload, workspace, *, timeout=600):
    """JSON stdin/stdout; capture sensitive diagnostics only in the private room."""
    validate_command(command)
    if command is None:
        return {"status": "skipped", "category": "executor_unavailable"}
    workspace = Path(workspace)
    workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
    request = {**payload, "protocol": "nodal-execution/1", "request_id": str(uuid.uuid4())}
    private_json(workspace / "request.json", request)
    # The process receives stdin, not paths into another executor's workspace.
    # Inherited authentication stays with the customer; no environment is logged.
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, cwd=workspace, start_new_session=True)
    except OSError:
        return {"status": "blocked", "category": "executor_unavailable"}
    try:
        stdout, stderr = process.communicate(json.dumps(request, allow_nan=False), timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kernels/executors may have children; terminate the task's process group.
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.communicate()
        return {"status": "blocked", "category": "executor_timeout"}
    private_json(workspace / "diagnostics.json", {"exit_code": process.returncode, "stderr": stderr})
    if process.returncode:
        return {"status": "blocked", "category": "executor_failed"}
    try:
        receipt = strict_json(stdout)
    except (ValueError, TypeError):
        return {"status": "blocked", "category": "invalid_executor_json"}
    if not isinstance(receipt, dict) or receipt.get("request_id") != request["request_id"]:
        return {"status": "blocked", "category": "receipt_request_mismatch"}
    private_json(workspace / "receipt.json", receipt)
    if receipt.get("status") in ("blocked", "skipped"):
        return {"status": receipt["status"], "category": "executor_reported_" + receipt["status"]}
    if receipt.get("status") != "ok":
        return {"status": "blocked", "category": "invalid_executor_status"}
    return receipt


def execution_problem(receipt, request):
    """Validate execution attestations before treating rows as evidence."""
    if receipt.get("status") != "ok":
        return receipt.get("category", "execution_not_available")
    for key in ("executed", "read_only", "fresh_session", "immutable_input"):
        if receipt.get(key) is not True:
            return "missing_" + key + "_attestation"
    for key in ("input_fingerprint", "as_of", "context_hash"):
        if receipt.get(key) != request.get(key):
            return key + "_mismatch"
    if request["role"] == "reference" and receipt.get("source_hash") != request["source_hash"]:
        return "source_hash_mismatch"
    if request["role"] == "answer" and receipt.get("reference_access") is not False:
        return "independence_not_attested"
    if not isinstance(receipt.get("session_id"), str) or not receipt["session_id"].strip():
        return "session_identity_missing"
    if not isinstance(receipt.get("environment"), dict) or not receipt["environment"]:
        return "environment_receipt_missing"
    if not isinstance(receipt.get("rows"), list) or not all(isinstance(r, dict) for r in receipt["rows"]):
        return "rows_missing"
    if not isinstance(receipt.get("columns"), list) or not all(isinstance(c, str) for c in receipt["columns"]):
        return "column_schema_missing"
    if len(receipt["columns"]) != len(set(receipt["columns"])) or any(
            set(row) != set(receipt["columns"]) for row in receipt["rows"]):
        return "inconsistent_column_schema"
    return None
