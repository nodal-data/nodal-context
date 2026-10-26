"""Format-neutral, one-shot execution of an approved read-only query.

Customer adapters enforce database privileges and historical snapshots. The
package rejects parsed writes/multiple statements; it is not a SQL sandbox.
"""
import hashlib
import logging
import re

from .execution import digest, invoke
from .grader import grade_answer


def read_only_sql(sql, warehouse):
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        return "sql_parser_unavailable"
    dialect = {"postgresql": "postgres", "sqlserver": "tsql"}.get(warehouse, warehouse)
    if re.search(r"<[A-Za-z_][A-Za-z0-9_]*>", sql):
        return "unbound_sql_placeholder"
    logger = logging.getLogger("sqlglot")
    disabled = logger.disabled
    try:
        logger.disabled = True  # parser fallback warnings can contain decrypted SQL
        statements = sqlglot.parse(sql, read=dialect)
    except ValueError:
        return "sql_dialect_unsupported"
    except sqlglot.errors.SqlglotError:
        return "sql_unparsed"
    finally:
        logger.disabled = disabled
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return "sql_multiple_statements"
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return "sql_not_read_only"
    prohibited = tuple(getattr(exp, name) for name in (
        "DDL", "DML", "Command", "Into", "Copy", "Lock", "Transaction", "Execute", "Grant", "Revoke")
        if hasattr(exp, name))
    if any(isinstance(node, prohibited) for node in tree.walk()):
        return "sql_not_read_only"
    return None


def execute_seed(seed, query_path, warehouse, parameters, workspace, *, executor, judge=None,
                 method=None, timeout=600):
    """Return a sanitized result and private component evidence, never execute on import."""
    try:
        raw = query_path.read_bytes()
        sql = raw.decode("utf-8")
    except (UnicodeError, OSError):
        return {"status": "skipped", "category": "query_unreadable"}, {}
    problem = read_only_sql(sql, warehouse)
    if problem:
        return {"status": "skipped", "category": problem}, {}
    snapshot = seed["expected"]["kind"] == "value_at_snapshot"
    request = {"role": "regression", "seed_id": seed["id"], "query_path": str(query_path),
               "query_hash": "sha256:" + hashlib.sha256(raw).hexdigest(), "warehouse": warehouse,
               "parameters": parameters, "parameters_hash": digest(parameters),
               "as_of": seed["expected"].get("as_of"), "require_historical_snapshot": snapshot,
               "require_read_only": True}
    receipt = invoke(executor, request, workspace / "execute", timeout=timeout)
    if receipt.get("status") != "ok":
        return {"status": "skipped", "category": receipt.get("category", "executor_unavailable")}, {}
    if receipt.get("executed") is not True or receipt.get("read_only") is not True:
        return {"status": "skipped", "category": "execution_not_attested"}, {}
    for key in ("query_hash", "warehouse", "parameters_hash"):
        if receipt.get(key) != request[key]:
            return {"status": "skipped", "category": "execution_binding_mismatch"}, {}
    # Never substitute today's data when a historical snapshot is unavailable.
    if snapshot and (receipt.get("historical_snapshot") is not True or receipt.get("as_of") != request["as_of"]):
        return {"status": "skipped", "category": "historical_snapshot_unavailable"}, {}
    rows, columns = receipt.get("rows"), receipt.get("columns")
    if (not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows) or
            not isinstance(columns, list) or not all(isinstance(c, str) for c in columns) or
            len(columns) != len(set(columns)) or any(set(r) != set(columns) for r in rows)):
        return {"status": "skipped", "category": "execution_rows_invalid"}, {}
    execution = {"status": "ok", "rows": rows, "columns": columns, "as_of": receipt.get("as_of")}
    if snapshot:
        reference = seed["expected"]["value"]
        if isinstance(reference, dict):
            if len(rows) != 1:
                return {"status": "fail", "category": "snapshot_shape_mismatch"}, {}
            execution["value"] = rows[0]
        elif not isinstance(reference, list):
            if len(rows) != 1 or len(columns) != 1:
                return {"status": "fail", "category": "snapshot_shape_mismatch"}, {}
            execution["value"] = rows[0][columns[0]]
    answer = {"outcome": "answer", "sql": sql,
              "explanation": receipt.get("explanation", ""), "disclosures": receipt.get("disclosures", []),
              "assumptions": receipt.get("assumptions", [])}
    counter = 0
    def judge_fn(evidence, obligation):
        nonlocal counter
        counter += 1
        verdict = invoke(judge, {"role": "judge", "evidence": evidence, "obligations": obligation},
                         workspace / ("judge-" + str(counter)), timeout=timeout)
        return verdict.get("verdict") if verdict.get("status") == "ok" else None
    verdict = grade_answer(seed["expected"], answer, judge_fn if judge else None, method=method, execution=execution)
    category = {"pass": "checks_passed", "fail": "grading_failed", "skipped": "grading_incomplete"}[verdict.status]
    return {"status": verdict.status, "category": category}, {"components": verdict.components, "reason": verdict.reason}
