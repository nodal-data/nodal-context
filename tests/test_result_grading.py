#!/usr/bin/env python3
"""Typed result comparison, honest partial grading and separate denominators."""
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval_harness.grader import compare_snapshot, compare_value, grade_answer, PASS, FAIL, SKIPPED
from eval_harness.report import render


def run_tests():
    expected = {"kind": "value_at_snapshot", "as_of": "2026-10-01", "key_columns": ["cohort"],
                "value": [{"cohort": "a", "rate": 0.5}, {"cohort": "b", "rate": None}],
                "tolerance": {"absolute": 0.001}}
    rows = [{"cohort": "b", "rate": None}, {"cohort": "a", "rate": 0.5005}]
    assert compare_snapshot(rows, expected).status == PASS
    for bad in ([rows[0], rows[0]], rows[:1], [{"rate": 0.5}, rows[0]],
                [{"cohort": "a", "rate": True}, rows[0]],
                [{"cohort": "a", "rate": float("nan")}, rows[0]]):
        assert compare_snapshot(bad, expected).status == FAIL
    assert compare_value(1, True).status == FAIL
    assert compare_value(0, None).status == FAIL
    assert compare_value(10**500, 10**500).status == PASS
    assert compare_value(1, 1, {"absolute": -1}).status == FAIL
    assert compare_value(1, 1, "invalid").status == FAIL
    assert compare_snapshot(rows, {"value": expected["value"]}).status == FAIL
    # Numeric row keys use the same equality as numeric snapshot values.
    assert compare_snapshot([{"id": 1.0}], {"value": [{"id": 1}], "key_columns": ["id"]}).status == PASS

    seen = []
    def judge(evidence, obligation):
        seen.append(obligation["kind"])
        return {"passed": True}
    answer = {"outcome": "answer", "sql": "SELECT ...", "explanation": "Windows disclosed"}
    execution = {"status": "ok", "as_of": expected["as_of"], "rows": rows}
    assert grade_answer(expected, answer, judge).status == SKIPPED
    assert not seen
    assert grade_answer(expected, answer, judge, execution=execution).status == PASS
    assert grade_answer(expected, answer, judge, execution={**execution, "as_of": "other"}).status == SKIPPED
    # A model's claimed rows are not trusted execution evidence.
    assert grade_answer(expected, {**answer, "execution": execution}, judge).status == SKIPPED
    method = {"decisions": [{"id": "identity", "rule": "Canonical customers"}],
              "output": {"columns": ["returned", "cohort_size", "rate"], "must_state": ["windows"]},
              "checks": ["returned <= cohort_size for every row", "rate is null wherever cohort_size = 0"]}
    shape = {"kind": "sql_shape", "must_include": ["canonical identity"]}
    result = grade_answer(shape, answer, judge, method=method)
    assert result.status == SKIPPED and result.components["decisions"]["status"] == PASS
    evidence = {"status": "ok", "rows": [{"returned": 0, "cohort_size": 0, "rate": None}]}
    assert grade_answer(shape, answer, judge, method=method, execution=evidence).status == PASS
    for change in ({"returned": 1}, {"rate": 0}, {"cohort_size": "0"}):
        bad = {**evidence, "rows": [{**evidence["rows"][0], **change}]}
        assert grade_answer(shape, answer, judge, method=method, execution=bad).status == FAIL
    assert grade_answer(shape, answer, judge, method=method,
                        execution={"status": "ok", "rows": []}).status == SKIPPED
    assert grade_answer(shape, answer, lambda *_: {"passed": "yes"}).status == SKIPPED
    assert grade_answer(shape, answer, None).status == SKIPPED
    missing_disclosure = lambda evidence, obligation: {"passed": obligation["kind"] != "method_disclosures"}
    assert grade_answer(shape, answer, missing_disclosure, method=method, execution=evidence).status == FAIL

    negative = {"kind": "negative", "reason": "unresolved_semantics"}
    decline = {"outcome": "escalate", "reason": "unresolved_semantics", "explanation": "Choose an anchor."}
    assert grade_answer(negative, decline, judge).status == PASS
    for change in ({"sql": "SELECT 1"}, {"python": "print(1)"}, {"explanation": ""},
                   {"reason": "lack_data"}, {"outcome": "answer"}):
        assert grade_answer(negative, {**decline, **change}, judge).status == FAIL
    seen.clear()
    for explanation in (None, 42, True, [], ["Choose an anchor"], {}, {"reason": "ambiguous"}, " \n\t"):
        invalid = grade_answer(negative, {**decline, "explanation": explanation}, judge)
        assert invalid.status == FAIL
        assert "explain the reason" in invalid.reason
    assert grade_answer(negative, {k: v for k, v in decline.items() if k != "explanation"}, judge).status == FAIL
    assert not seen  # Malformed explanations fail before invoking the judge.
    report = render([{"domain": "test", "seeds": [
        {"question": "paired", "kind": "sql_shape", "off": FAIL, "on": PASS},
        {"question": "partial", "kind": "sql_shape", "off": PASS, "on": SKIPPED,
         "on_components": result.components},
        {"question": "negative", "kind": "negative", "off": PASS, "on": FAIL}]}])
    assert "Paired positive denominator: 1" in report and "(+100 pts)" in report
    assert "Escalation accuracy" in report and "context-on: 0% (0/1)" in report
    assert "on/output: 0/0 passed; 1 skipped" in report
    print("test_result_grading: OK")


if __name__ == "__main__":
    run_tests()
