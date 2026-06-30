"""Offline test for .ci/suggest.py parsing helpers — stdlib only, no API calls.

Only the pure helpers (affected_files, build_prompt) are exercised; the Anthropic
call path needs a key and network and is not tested here.

Run: python3 tests/test_suggest.py   (exit 0 = pass)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".ci"))
import suggest  # noqa: E402

REPORT = """## Context drift detected

### domain: orders
_Affected context files: domains/orders/domain.yaml, domains/orders/reference.md_
  - **fct_orders** (dbt_core)
    - columns added: order_id

### domain: billing
_Affected context files: domains/billing/metrics.yaml_
  - **fct_invoices** (dbt_core)
    - tests removed: unique:invoice_id
"""


def run():
    # --- affected_files: extracts, dedupes, preserves order ----------------
    files = suggest.affected_files(REPORT)
    assert files == [
        "domains/orders/domain.yaml",
        "domains/orders/reference.md",
        "domains/billing/metrics.yaml",
    ], files

    # dedupe: a path mentioned twice appears once
    dup = REPORT + "\nsee domains/orders/domain.yaml again\n"
    assert suggest.affected_files(dup).count("domains/orders/domain.yaml") == 1

    # --- build_prompt: inlines real files, marks missing ones --------------
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        (repo / "domains" / "orders").mkdir(parents=True)
        (repo / "domains" / "orders" / "domain.yaml").write_text("name: orders\n")
        (repo / "domains" / "orders" / "reference.md").write_text("# orders\n")
        # billing/metrics.yaml intentionally absent
        prompt = suggest.build_prompt(REPORT, repo)
        assert "name: orders" in prompt
        assert "# Drift report" in prompt
        assert "(missing on disk)" in prompt  # billing file not created

    print("test_suggest: OK")


if __name__ == "__main__":
    run()
