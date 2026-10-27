"""Format-neutral grading with explicit component results and execution limits.

No input is evaluated as code. Model judgment is injected; snapshot comparisons
and simple row relationships are deterministic. Missing evidence is skipped.
"""
from dataclasses import dataclass, field
import json
import math
import re

PASS, FAIL, SKIPPED = "pass", "fail", "skipped"


@dataclass
class Result:
    status: str
    reason: str = ""
    components: dict = field(default_factory=dict)


def _numeric(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool)


def _finite(value):
    return _numeric(value) and (isinstance(value, int) or math.isfinite(value))


def compare_value(actual, expected, tolerance=None, path="value"):
    """Compare typed JSON values; non-finite numbers are invalid evidence."""
    tolerance = tolerance or {}
    if not isinstance(tolerance, dict):
        return Result(FAIL, "invalid numeric tolerance")
    absolute, relative = tolerance.get("absolute", 0), tolerance.get("relative", 0)
    if any(not _finite(v) or v < 0 for v in (absolute, relative)):
        return Result(FAIL, "invalid numeric tolerance")
    if _numeric(expected) and _numeric(actual):
        if not _finite(expected) or not _finite(actual):
            return Result(FAIL, f"{path}: non-finite number")
        if abs(actual - expected) > max(absolute, relative * abs(expected)):
            return Result(FAIL, f"{path}: numeric mismatch")
        return Result(PASS)
    if type(actual) is not type(expected):
        return Result(FAIL, f"{path}: type mismatch")
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            return Result(FAIL, f"{path}: column/object-key mismatch")
        for key in sorted(expected):
            result = compare_value(actual[key], expected[key], tolerance, f"{path}.{key}")
            if result.status != PASS:
                return result
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            return Result(FAIL, f"{path}: length mismatch")
        for index, (a, e) in enumerate(zip(actual, expected)):
            result = compare_value(a, e, tolerance, f"{path}[{index}]")
            if result.status != PASS:
                return result
    elif actual != expected:
        return Result(FAIL, f"{path}: value mismatch")
    return Result(PASS)


def compare_snapshot(actual, expected):
    if "value" not in expected:
        return Result(FAIL, "snapshot has no expected value")
    reference = expected["value"]
    tolerance = expected.get("tolerance", {})
    if not isinstance(reference, list):
        return compare_value(actual, reference, tolerance)
    if not isinstance(actual, list) or not all(isinstance(r, dict) for r in actual + reference):
        return Result(FAIL, "tabular snapshots require arrays of row objects")
    keys = expected.get("key_columns", [])
    if max(len(actual), len(reference)) > 1 and not keys:
        return Result(FAIL, "multiple snapshot rows require key_columns")
    if not keys:
        return compare_value(actual, reference, tolerance)
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys) or len(keys) != len(set(keys)):
        return Result(FAIL, "invalid comparison keys")
    def index(rows):
        out = {}
        for row in rows:
            if any(k not in row for k in keys):
                raise ValueError("comparison key missing from row")
            values = [row[k] for k in keys]
            if any(isinstance(v, (dict, list)) or (_numeric(v) and not _finite(v)) for v in values):
                raise ValueError("comparison keys must be finite scalar values")
            # A string '1', boolean true, and integer 1 are distinct keys.
            key = tuple(("number", v) if _numeric(v) else (type(v).__name__, v) for v in values)
            if key in out:
                raise ValueError("duplicate comparison key")
            out[key] = row
        return out
    try:
        actual_index, reference_index = index(actual), index(reference)
    except ValueError as exc:
        return Result(FAIL, str(exc))
    if actual_index.keys() != reference_index.keys():
        return Result(FAIL, "snapshot row-key sets differ")
    for key in reference_index:
        verdict = compare_value(actual_index[key], reference_index[key], tolerance, "row")
        if verdict.status != PASS:
            return verdict
    return Result(PASS, "snapshot rows match by declared keys and tolerance")


def _judge(judge_fn, evidence, obligations):
    if judge_fn is None:
        return Result(SKIPPED, "judge unavailable")
    try:
        verdict = judge_fn(evidence, obligations)
    except Exception:
        return Result(SKIPPED, "judge failed; no verdict")
    if not isinstance(verdict, dict) or type(verdict.get("passed")) is not bool:
        return Result(SKIPPED, "judge returned an invalid verdict")
    return Result(PASS if verdict["passed"] else FAIL, str(verdict.get("reason", "")))


def _combined(components):
    values = list(components.values())
    failed = next((r for r in values if r.status == FAIL), None)
    skipped = next((r for r in values if r.status == SKIPPED), None)
    return Result(FAIL if failed else SKIPPED if skipped else PASS,
                  (failed or skipped).reason if (failed or skipped) else "all required checks passed",
                  {k: {"status": v.status, "reason": v.reason} for k, v in components.items()})


def _direct_check(check, rows):
    """Recognize a deliberately small relationship vocabulary, never eval()."""
    comparison = re.fullmatch(r"([A-Za-z_]\w*)\s*(<=|>=|<|>|==|=)\s*([A-Za-z_]\w*)\s*(?:for every row)?", check.strip())
    null_rule = re.fullmatch(r"([A-Za-z_]\w*) is null (?:wherever|when|where) ([A-Za-z_]\w*)\s*=\s*0", check.strip(), re.I)
    if comparison:
        left, op, right = comparison.groups()
        operations = {"<=": lambda a,b:a <= b, ">=":lambda a,b:a >= b, "<":lambda a,b:a < b,
                      ">":lambda a,b:a > b, "=":lambda a,b:a == b, "==":lambda a,b:a == b}
        for row in rows:
            if left not in row or right not in row:
                return Result(FAIL, "relationship column missing")
            a, b = row[left], row[right]
            if not _finite(a) or not _finite(b):
                return Result(FAIL, "relationship needs finite numeric values")
            if not operations[op](a, b):
                return Result(FAIL, "row relationship violated")
        return Result(PASS)
    if null_rule:
        value, denominator = null_rule.groups()
        for row in rows:
            if value not in row or denominator not in row:
                return Result(FAIL, "null-policy column missing")
            if not _finite(row[denominator]):
                return Result(FAIL, "null-policy denominator must be numeric")
            if row[denominator] == 0 and row[value] is not None:
                return Result(FAIL, "empty-population null policy violated")
        return Result(PASS)
    return None


def grade_answer(expected, answer, judge_fn, *, method=None, execution=None):
    """Grade an answer; execution is trusted customer evidence, never LLM claims.

    execution: {status: 'ok', value?, rows?, columns?, as_of?}. No implicit runs.
    Generic callers may still pass legacy SQL strings through grade().
    """
    answer = {"outcome": "answer", "sql": answer, "assumptions": []} if isinstance(answer, str) else answer
    if not isinstance(answer, dict):
        return Result(FAIL, "invalid answer object")
    kind = (expected or {}).get("kind", "")
    outcome = answer.get("outcome", "answer")
    if kind == "negative":
        if outcome not in ("decline", "escalate") or answer.get("reason") != expected.get("reason"):
            return Result(FAIL, "incorrect escalation outcome or reason")
        explanation = answer.get("explanation")
        if (answer.get("sql") or answer.get("python") or
                not isinstance(explanation, str) or not explanation.strip()):
            return Result(FAIL, "decline/escalation must explain the reason without proposing executable analysis")
        return _judge(judge_fn, answer, {"kind": "negative", "reason": expected["reason"],
                      "obligation": "Explain the matching reason; do not invent a result or claim execution."})
    if kind not in ("sql_shape", "semantic_entity", "value_at_snapshot"):
        return Result(SKIPPED, f"unsupported expected.kind: {kind or '(none)'}")
    if outcome != "answer":
        return Result(FAIL, "positive seed was not answered")
    components = {}
    if kind in ("sql_shape", "semantic_entity") or expected.get("must_include") or expected.get("must_exclude"):
        code = answer.get("sql") or answer.get("python")
        components["shape"] = (_judge(judge_fn, code, expected) if code else Result(FAIL, "no analysis implementation"))
    if kind == "value_at_snapshot":
        if not execution or execution.get("status") != "ok":
            components["snapshot"] = Result(SKIPPED, "needs execution evidence (value_at_snapshot)")
        elif not expected.get("as_of") or execution.get("as_of") != expected["as_of"]:
            components["snapshot"] = Result(SKIPPED, "execution does not establish the pinned as_of date")
        elif "value" not in execution and "rows" not in execution:
            components["snapshot"] = Result(SKIPPED, "execution result missing")
        else:
            components["snapshot"] = compare_snapshot(execution.get("value", execution.get("rows")), expected)
    if method is not None:
        implementation = answer.get("sql") or answer.get("python")
        components["implementation"] = (Result(PASS) if isinstance(implementation, str) and implementation.strip()
                                        else Result(FAIL, "method answer has no analysis implementation"))
        output = method.get("output", {})
        decisions = method.get("decisions", [])
        if not decisions:
            components["decisions"] = Result(SKIPPED, "method without decisions")
        else:
            components["decisions"] = _judge(judge_fn, answer, {"kind": "method_decisions", "decisions": decisions})
        obligations = output.get("must_state", [])
        if obligations:
            components["disclosures"] = _judge(judge_fn, {"explanation": answer.get("explanation", ""),
                "disclosures": answer.get("disclosures", []), "assumptions": answer.get("assumptions", [])},
                {"kind": "method_disclosures", "must_state": obligations})
        if not execution or execution.get("status") != "ok":
            components["output"] = Result(SKIPPED, "method result checks need execution evidence")
            for i, check in enumerate(method.get("checks", [])):
                components[f"check:{i}"] = Result(SKIPPED, "method relationship needs execution evidence")
        else:
            rows = execution.get("rows", execution.get("value"))
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                components["output"] = Result(FAIL, "method output must be row objects")
            else:
                required = set(output.get("columns", [])) - set(output.get("optional_columns", []))
                columns = set(execution.get("columns", []))
                if not rows and not required.issubset(columns):
                    components["output"] = Result(SKIPPED, "empty result needs explicit column schema")
                elif any(not required.issubset(row) for row in rows):
                    components["output"] = Result(FAIL, "required output column missing")
                else:
                    components["output"] = Result(PASS)
                for i, check in enumerate(method.get("checks", [])):
                    direct = _direct_check(check, rows)
                    components[f"check:{i}"] = direct or _judge(judge_fn,
                        {"rows": rows, "answer": answer, "execution": execution},
                        {"kind": "method_relationship", "check": check,
                         "obligation": "Use actual result evidence. Unestablished relationships must not pass."})
    return _combined(components)


def grade(expected, sql, judge_fn):
    return grade_answer(expected, sql, judge_fn)
