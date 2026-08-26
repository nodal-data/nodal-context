"""Grade a generated answer against a seed's `expected`, keyed on `expected.kind`.

  sql_shape       -> LLM judge on must_include/must_exclude
  semantic_entity -> LLM judge on resolving to expected.entity
  value_at_snapshot -> SKIPPED (needs a live warehouse to produce the number; that's the
                       paid live-execution path, out of scope for the OSS one-shot runner)

The LLM call is injected as `judge_fn` so this module is pure and unit-testable offline.
"""
from dataclasses import dataclass

PASS, FAIL, SKIPPED = "pass", "fail", "skipped"


@dataclass
class Result:
    status: str          # pass | fail | skipped
    reason: str = ""


def grade(expected: dict, sql: str, judge_fn) -> Result:
    kind = (expected or {}).get("kind", "")
    if kind == "value_at_snapshot":
        return Result(SKIPPED, "needs warehouse (value_at_snapshot)")
    if kind not in ("sql_shape", "semantic_entity"):
        return Result(SKIPPED, f"unsupported expected.kind: {kind or '(none)'}")
    verdict = judge_fn(sql, expected) or {}
    return Result(PASS if verdict.get("passed") else FAIL, verdict.get("reason", ""))
