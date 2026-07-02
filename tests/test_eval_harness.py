"""Offline tests for the eval_harness runner — the LLM client is mocked, no key/network.

Needs PyYAML (the acf adapter parses seeds); self-skips with exit 0 if it's absent.

Run: python3 tests/test_eval_harness.py   (exit 0 = pass/skip)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval_harness import adapters, client, grader, report, run  # noqa: E402
from eval_harness.grader import PASS, FAIL, SKIPPED  # noqa: E402

HEALTHCARE = ROOT / "examples" / "example-healthcare-company"


def run_tests():
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("test_eval_harness: PyYAML missing; skipped")
        return

    # --- adapter: ACF -> NCR ----------------------------------------------------
    ncr = adapters.get_builder("acf")(HEALTHCARE, ["session-financials"])
    assert ncr.domains() == ["session-financials"], ncr.domains()
    confirmed = ncr.seeds_for("session-financials", "confirmed")
    assert len(confirmed) == 2, [s.question for s in confirmed]   # both example seeds confirmed
    kinds = sorted(s.kind for s in confirmed)
    assert kinds == ["sql_shape", "value_at_snapshot"], kinds
    ctx = ncr.context_for("session-financials")
    # context-on payload carries the routing triggers the seeds test
    assert "Payer X" in ctx and "45-day" in ctx, "context blob missing routing triggers"

    # unknown adapter errors; planned-but-unbuilt raises NotImplementedError
    try:
        adapters.get_builder("nope"); assert False
    except ValueError:
        pass
    try:
        adapters.get_builder("dbt"); assert False
    except NotImplementedError:
        pass

    # --- grader ----------------------------------------------------------------
    sql_shape = {"kind": "sql_shape", "must_include": ["x"], "must_exclude": ["y"]}
    assert grader.grade(sql_shape, "SELECT 1", lambda s, e: {"passed": True, "reason": "ok"}).status == PASS
    bad = grader.grade(sql_shape, "SELECT 1", lambda s, e: {"passed": False, "reason": "missing x"})
    assert bad.status == FAIL and bad.reason == "missing x"
    # value_at_snapshot is skipped without calling the judge
    called = []
    skip = grader.grade({"kind": "value_at_snapshot", "value": 0.9}, "SELECT 1",
                        lambda s, e: called.append(1) or {"passed": True})
    assert skip.status == SKIPPED and not called

    # --- report rendering ------------------------------------------------------
    dr = [{
        "domain": "session-financials", "drafts": 1,
        "seeds": [
            {"question": "Qa", "kind": "sql_shape", "off": FAIL, "on": PASS, "on_reason": ""},
            {"question": "Qb", "kind": "sql_shape", "off": FAIL, "on": FAIL,
             "on_reason": "forgot the 45-day cutoff"},
            {"question": "Qc", "kind": "value_at_snapshot", "off": SKIPPED,
             "on": SKIPPED, "on_reason": ""},
        ],
    }]
    text = report.render(dr)
    assert "context-off → 0%" in text          # 0 of 2 gradable
    assert "context-on  → 50%" in text          # 1 of 2 gradable
    assert "(+50 pts)" in text
    assert "1 value_at_snapshot skipped" in text
    assert 'forgot the 45-day cutoff  [sql_shape]' in text   # punch-list only the on-fail
    assert "Qa" not in text                      # passing seed not in punch-list

    # --- run.main with a fully mocked client -----------------------------------
    # context-off always "misses" the exclusion; context-on always passes.
    def fake_generate(question, context_text=None, model=None):
        return {"sql": "SELECT 1 -- with-context" if context_text else "SELECT 1", "assumptions": []}

    def fake_judge(sql, expected, model=None):
        return {"passed": "with-context" in sql, "reason": "" if "with-context" in sql else "missed caveat"}

    orig = (client.available, client.generate, client.judge)
    client.available = lambda: True
    client.generate = fake_generate
    client.judge = fake_judge
    try:
        rc = run.main(["--adapter", "acf", "--root", str(HEALTHCARE),
                       "--domains", "session-financials", "--report", "pr-comment"])
        assert rc == 0
        # no-key path: graceful skip, exit 0
        client.available = lambda: False
        assert run.main(["--root", str(HEALTHCARE), "--domains", "session-financials"]) == 0
    finally:
        client.available, client.generate, client.judge = orig

    print("test_eval_harness: OK")


if __name__ == "__main__":
    run_tests()
