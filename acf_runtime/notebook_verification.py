"""ACF notebook comparison orchestration, with private reference/answer requests."""
from datetime import date
from pathlib import Path
import uuid

from .loader import load_context, Schemas
from .notebooks import content_hash
from .regression import seed_fingerprint
from .verified import contained
from eval_harness.execution import digest, execution_problem, invoke, private_json, strict_json, validate_command
from eval_harness.grader import grade_answer, compare_snapshot, PASS, FAIL, SKIPPED


def method_context(registry, method_name):
    method = registry.nodes.get("method:" + method_name.removeprefix("methods/").removeprefix("method:"))
    if not method or method.kind != "method":
        raise ValueError("method does not exist")
    if method.effective_status != "confirmed" or method.blocking_reasons:
        raise ValueError("method and dependencies must be eligible and unblocked; use explicit branch-test mode for proposed context")
    selected, pending = {}, [method.id]
    while pending:
        key = pending.pop()
        if key in selected:
            continue
        node = registry.nodes[key]
        # Source provenance may disclose notebook location; it is not needed to answer.
        data = {k: v for k, v in node.data.items() if k not in ("provenance", "approver", "confirmed_at")}
        selected[key] = {"definition": data, "body": node.body}
        pending.extend(dep for dep in node.dependencies if dep in registry.nodes and not dep.startswith("seed:"))
    # Entity definitions may be required without an explicit decision reference.
    for node in registry.nodes.values():
        if node.kind == "entity" and node.domain in ("", method.domain):
            selected[node.id] = {"definition": node.data}
    return method, selected


def validate_case(case, method, registry):
    required = {"parameters", "as_of", "input_snapshot", "inputs", "timezone", "random_seed", "output", "key_columns"}
    if not isinstance(case, dict) or required - case.keys() or case.keys() - required - {"tolerance", "metrics"}:
        raise ValueError("case requires parameters, as_of, input_snapshot, inputs, timezone, random_seed, output and key_columns; optional tolerance and metrics")
    for key in ("as_of", "input_snapshot", "timezone", "output"):
        if not isinstance(case[key], str) or not case[key].strip():
            raise ValueError("case " + key + " must be nonempty text")
    date.fromisoformat(case["as_of"])
    if not isinstance(case["inputs"], dict) or not isinstance(case["parameters"], dict):
        raise ValueError("inputs and parameters must be objects")
    names = {p["name"] for p in method.data["parameters"]}
    parameters = {p["name"]: p["default"] for p in method.data["parameters"] if "default" in p}
    parameters.update(case["parameters"])
    if set(parameters) != names:
        raise ValueError("supply every method parameter without extra bindings")
    composed = sorted(k for k in method.dependencies if k.startswith("metric:"))
    selected = case.get("metrics")
    if selected is None:
        if len(composed) != 1:
            raise ValueError("select the resolved metrics for this parameterization in case.metrics")
        selected = composed
    if not isinstance(selected, list) or not selected or not all(isinstance(m, str) for m in selected):
        raise ValueError("case.metrics must be a nonempty array of reviewed metric references")
    resolved = []
    for ref in selected:
        node = registry.resolve(ref, method.domain)
        if not node or node.id not in composed:
            raise ValueError("case.metrics must select metrics composed by the method")
        resolved.append(node.id)
    if len(set(resolved)) != len(resolved):
        raise ValueError("case.metrics contains duplicate references")
    for parameter in method.data["parameters"]:
        if parameter.get("dimension"):
            value = parameters[parameter["name"]]
            if not isinstance(value, str) or any(value not in registry.nodes[m].dimensions for m in resolved):
                raise ValueError("dimension binding must be supported by every resolved metric")
    keys = case["key_columns"]
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k for k in keys) or len(keys) != len(set(keys)):
        raise ValueError("select nonempty, unique row key columns before executing")
    if not set(keys).issubset(method.data["output"]["columns"]):
        raise ValueError("comparison keys must be declared method output columns")
    if case["random_seed"] is not None and type(case["random_seed"]) is not int:
        raise ValueError("random_seed must be an integer or null")
    from eval_harness.grader import compare_value
    if compare_value(0, 0, case.get("tolerance")).status != PASS:
        raise ValueError("invalid comparison tolerance")
    return {**case, "parameters": parameters, "metrics": sorted(resolved)}


def _schema_dir(root):
    return root / "schemas" if (root / "schemas").is_dir() else Path(__file__).resolve().parents[1] / "schemas"


def verify(root, notebook, method_name, question, case, *, reference_command=None,
           answer_command=None, judge_command=None, timeout=600):
    root, notebook = Path(root).resolve(), Path(notebook).resolve()
    for command in (reference_command, answer_command, judge_command):
        validate_command(command)
    registry = load_context(root)
    if registry.errors:
        raise ValueError("context must validate before notebook verification")
    method, context = method_context(registry, method_name)
    if not isinstance(question, str) or not question.strip():
        raise ValueError("a business question is required")
    case = validate_case(case, method, registry)
    source_hash, context_hash = content_hash(notebook.read_bytes()), digest(context)
    run_id = "notebook-" + uuid.uuid4().hex
    directory = root / ".nodal" / "notebook-runs" / run_id
    if not directory.resolve().is_relative_to(root):
        raise ValueError("local evidence path escapes root")
    directory.mkdir(mode=0o700, parents=True)
    # Keys/output/tolerances are comparison-only; the answering agent sees the
    # method output contract, never a reference-output selector or expectation.
    common = {"input_fingerprint": digest({k: case[k] for k in (
        "parameters", "metrics", "as_of", "input_snapshot", "inputs", "timezone", "random_seed")}),
        "parameters": case["parameters"], "as_of": case["as_of"], "input_snapshot": case["input_snapshot"],
        "inputs": case["inputs"], "timezone": case["timezone"], "random_seed": case["random_seed"],
        "context_hash": context_hash, "resolved_metrics": case["metrics"], "require_read_only": True}
    reference_request = {**common, "role": "reference", "notebook": str(notebook),
                         "source_hash": source_hash, "output": case["output"],
                         "requirements": "Preflight side effects; fresh kernel; execute required cells in order; no cached output or altered reference logic."}
    answer_request = {**common, "role": "answer", "question": question, "context": context,
                      "requirements": "Use a fresh independent agent context; derive and execute SQL/Python using only supplied method/definitions and inputs; do not access notebook/reference/seed answers."}
    report = {"protocol": "nodal-notebook-verification/1", "run_id": run_id, "method": method.data["name"],
              "domain": method.domain, "question": question, "case": case, "source_path": str(notebook),
              "source_hash": source_hash, "context_hash": context_hash, "human_approved": False,
              "status": "skipped", "category": "execution_pending"}
    private_json(directory / "plan.json", report)
    reference = invoke(reference_command, reference_request, directory / "reference", timeout=timeout)
    answer = invoke(answer_command, answer_request, directory / "answer", timeout=timeout)
    problems = [p for p in (execution_problem(reference, reference_request), execution_problem(answer, answer_request)) if p]
    if problems:
        report.update(status="skipped" if all(r.get("status") == "skipped" for r in (reference, answer)) else "blocked",
                      category=",".join(problems))
    elif reference["session_id"] == answer["session_id"]:
        report.update(status="blocked", category="reference_and_answer_share_session")
    else:
        expected = {"kind": "value_at_snapshot", "value": reference["rows"], "as_of": case["as_of"],
                    "key_columns": case["key_columns"], "tolerance": case.get("tolerance", {})}
        judge_counter = 0
        def judge(evidence, obligations):
            nonlocal judge_counter
            judge_counter += 1
            receipt = invoke(judge_command, {"role": "judge", "evidence": evidence, "obligations": obligations,
                "requirements": "Independently review actual implementation/results against these obligations; do not pass unestablished claims."},
                directory / ("judge-" + str(judge_counter)), timeout=timeout)
            return receipt.get("verdict") if receipt.get("status") == "ok" else None
        # Validate the reference itself for duplicate keys/nonfinite values before comparison.
        reference_check = compare_snapshot(reference["rows"], expected)
        execution = {key: answer[key] for key in ("status", "rows", "columns", "as_of")}
        result = grade_answer(expected, answer.get("answer"), judge if judge_command else None,
                              method=method.data, execution=execution)
        report.update(status=result.status, category=result.reason, components=result.components,
                      expected=expected, reference_session=reference["session_id"], answer_session=answer["session_id"])
        if reference_check.status != PASS:
            report.update(status="blocked", category="invalid_reference: " + reference_check.reason)
        if reference["columns"] != answer["columns"] and set(reference["columns"]) != set(answer["columns"]):
            report.update(status="fail", category="output_column_sets_differ")
    # Catch edits during execution. Semantic dependency hash intentionally excludes approval/provenance.
    current = load_context(root)
    try:
        _, current_context = method_context(current, method_name)
        changed = current.errors or digest(current_context) != context_hash or content_hash(notebook.read_bytes()) != source_hash
    except (OSError, ValueError):
        changed = True
    if changed:
        report.update(status="blocked", category="source_or_context_changed_during_run")
    private_json(directory / "comparison.json", report)
    return directory, report


def confirm(root, report_path, *, seed_name, approver, confirmed_at, approved_sql=None):
    """Explicit human-confirmation operation. Run/comparison never calls this."""
    from .notebooks import SLUG
    import yaml
    root, report_path = Path(root).resolve(), Path(report_path).resolve()
    evidence_root = (root / ".nodal" / "notebook-runs").resolve()
    if not evidence_root.is_relative_to(root) or not report_path.is_relative_to(evidence_root):
        raise ValueError("confirmation requires a local notebook comparison report")
    report = strict_json(report_path.read_text())
    if report.get("status") != PASS or report.get("human_approved"):
        raise ValueError("only an unconfirmed passing comparison may be promoted")
    if not SLUG.fullmatch(seed_name) or not approver.strip():
        raise ValueError("provide a valid seed name and the actual human approver")
    date.fromisoformat(confirmed_at)
    registry = load_context(root)
    if registry.errors:
        raise ValueError("context must validate before confirmation")
    method, context = method_context(registry, report["method"])
    source = Path(report["source_path"])
    if digest(context) != report["context_hash"] or content_hash(source.read_bytes()) != report["source_hash"]:
        raise ValueError("source or method/dependencies changed; rerun verification")
    seed = {"question": report["question"], "intent": method.data["description"], "domain": method.domain,
            "approver": approver, "confirmed_at": confirmed_at, "provenance": "notebook",
            "ir": {"method": method.data["name"], "metrics": sorted(
                registry.nodes[k].domain + "." + registry.nodes[k].data["name"]
                for k in report["case"]["metrics"]), "parameters": report["case"]["parameters"]},
            "expected": report["expected"], "verification_source": {"kind": "notebook",
                "path": method.data.get("provenance", {}).get("path", source.name),
                "ref": report["source_hash"], "output": report["case"]["output"]}}
    if method.data.get("provenance", {}).get("repo"):
        seed["verification_source"]["repo"] = method.data["provenance"]["repo"]
    errors = Schemas(_schema_dir(root)).errors("evalseed", seed)
    if errors:
        raise ValueError("generated seed failed schema validation: " + errors[0].message)
    target = root / "evals" / "seeds" / (seed_name + ".seed.yaml")
    if not target.resolve().is_relative_to(root):
        raise ValueError("seed path escapes root")
    target.parent.mkdir(parents=True, exist_ok=True)
    approval_path = report_path.parent / ("approval-" + seed_name + ".json")
    if target.exists() or approval_path.exists():
        raise ValueError("seed or approval already exists; do not overwrite authored evidence")
    publication = None
    publication_files = {}
    if approved_sql is not None:
        from .verified import VerifiedSQL
        from eval_harness.regression import read_only_sql
        receipt = strict_json((report_path.parent / "answer" / "receipt.json").read_text())
        actual_sql = receipt.get("answer", {}).get("sql")
        payload = Path(approved_sql).read_bytes()
        if not isinstance(actual_sql, str) or not actual_sql.strip() or payload.decode("utf-8") != actual_sql:
            raise ValueError("approved SQL must exactly match the independently executed answer SQL")
        sources = {s["id"]: s.get("warehouse", registry.config["warehouse"]) for s in registry.config["lineage_sources"]}
        warehouses = {sources[source] for source, _ in method.lineage} or {registry.config["warehouse"]}
        if len(warehouses) != 1 or read_only_sql(actual_sql, next(iter(warehouses))):
            raise ValueError("approved SQL must be a supported single-warehouse read-only query")
        manager = VerifiedSQL(root, config=registry.config)
        query = "evals/verified/" + seed_name + ".sql"
        plain, cipher, _ = manager.paths(query)
        if plain.exists() or cipher.exists():
            raise ValueError("approved query artifact already exists; review it without overwriting")
        try:
            publication = manager.capture(query, payload)
        except Exception:
            # A failed ciphertext write may follow successful plaintext capture.
            if plain.is_file() and not plain.is_symlink() and plain.read_bytes() == payload:
                plain.unlink()
            raise
        publication_files = {p: p.read_bytes() for p in (plain, cipher) if p.is_file()}
        seed["verified_query_file"] = query
    created_seed = False
    try:
        with target.open("x") as stream:
            created_seed = True
            stream.write(yaml.safe_dump(seed, sort_keys=False, allow_unicode=True))
        confirmed_registry = load_context(root)
        if confirmed_registry.errors:
            raise ValueError("snapshot seed failed context validation")
        private_json(approval_path, {
            "seed": target.relative_to(root).as_posix(), "approver": approver, "confirmed_at": confirmed_at,
            "seed_fingerprint": seed_fingerprint(confirmed_registry, confirmed_registry.nodes["seed:" + target.name]),
            "comparison_hash": digest(report), "sql_publication": publication})
    except Exception:
        if created_seed:
            target.unlink(missing_ok=True)
        # Only remove artifacts created by this attempt and still byte-identical.
        for path, content in publication_files.items():
            if path.is_file() and not path.is_symlink() and path.read_bytes() == content:
                path.unlink()
        raise
    return target


def checked_evidence(root, seed, registry, report_path):
    """Explicit local freshness check; no execution, source fetch or authored write.

    A private receipt is customer evidence, not a cryptographic attestation. A
    clone without that receipt still has its historical human-confirmed snapshot.
    """
    root = Path(root).resolve()
    report_path = contained(root, report_path, ".nodal/notebook-runs")
    result = {"state": "notebook_evidence_unavailable", "verified": False,
              "source_revision_checked": False}
    try:
        report = strict_json(report_path.read_text())
        if not isinstance(report, dict) or report.get("protocol") != "nodal-notebook-verification/1":
            raise ValueError("invalid notebook report")
        approval_path = contained(root, (report_path.parent /
            ("approval-" + Path(seed["path"]).name.removesuffix(".seed.yaml") + ".json")).relative_to(root),
            ".nodal/notebook-runs")
        approval = strict_json(approval_path.read_text())
        node = registry.nodes[seed["id"]]
        if (not isinstance(approval, dict) or approval.get("seed") != node.path
                or approval.get("comparison_hash") != digest(report)
                or approval.get("approver") != node.data.get("approver")
                or approval.get("confirmed_at") != node.data.get("confirmed_at")
                or approval.get("seed_fingerprint") != seed_fingerprint(registry, node)):
            return {**result, "state": "stale_verification", "stale_reasons": ["notebook_approval_or_context_changed"]}
        if report.get("status") != PASS:
            return {**result, "state": "stale_verification", "stale_reasons": ["notebook_comparison_not_passing"]}
        method, context = method_context(registry, report["method"])
        if digest(context) != report["context_hash"]:
            return {**result, "state": "stale_verification", "stale_reasons": ["notebook_context_changed"]}
        source = Path(report["source_path"])
        if source.suffix != ".ipynb" or not source.is_absolute():
            raise ValueError("invalid notebook source")
        current_hash = content_hash(source.read_bytes())
        result["source_revision_checked"] = True
        if (current_hash != report["source_hash"] or
                seed.get("verification_source", {}).get("ref") != report["source_hash"]):
            return {**result, "state": "stale_verification", "stale_reasons": ["notebook_source_changed"]}
        return {**result, "state": "notebook_checked_snapshot", "verified": True}
    except (OSError, ValueError, KeyError, TypeError):
        return {**result, "stale_reasons": ["notebook_evidence_or_source_unavailable"]}
