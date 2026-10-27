"""Synthetic live AI-to-notebook acceptance, explicitly selected by --live-ai."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_fixtures import context, metric, method, write
from acf_runtime.notebook_verification import verify
from eval_harness import client


def run():
    import nbformat
    if not client.available():
        raise RuntimeError("--live-ai requires the operator's ANTHROPIC_API_KEY")
    room = Path(tempfile.mkdtemp(prefix="nodal-notebook-ai-")).resolve()
    root = room / "context"
    context(root)
    write(root, "domains/sales/metrics/orders.yaml", metric())
    reviewed = method()
    reviewed.update(name="eligible-orders", description="Fictional eligible order counts by channel",
        aliases=[], parameters=[{"name": "start_date", "note": "Inclusive UTC date"},
                                {"name": "end_date", "note": "Exclusive UTC date"}],
        decisions=[{"id": "window", "rule": "Count orders where test is false and ordered_at is >= <start_date> and < <end_date>, grouped by channel.",
                    "without_this": "Test traffic and inconsistent date boundaries distort comparisons."}],
        checks=["orders >= 0 for every row"])
    reviewed["output"]["must_state"] = ["State the inclusive start date, exclusive end date and UTC timezone."]
    write(root, "methods/eligible-orders.md", reviewed,
          "## When to use\n\nEligible orders by channel.\n\n## Procedure\n\n"
          "1. Apply the `window` decision using <start_date> and <end_date>, then count orders by channel.\n")
    orders = [{"order_id": i, "channel": channel, "ordered_at": day, "test": test}
              for i, (channel, day, test) in enumerate([
                  ("web", "2026-09-01", False), ("web", "2026-09-15", False),
                  ("web", "2026-09-30", True), ("web", "2026-08-31", False),
                  ("web", "2026-10-01", False), ("store", "2026-09-15", False),
                  ("store", "2026-09-30", False), ("store", "2026-09-01", False),
                  ("store", "2026-10-01", False)], 1)]
    source = room / "reference.ipynb"
    notebook = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_code_cell("start_date = '2000-01-01'\nend_date = '2000-02-01'", metadata={"tags": ["parameters"]}),
        nbformat.v4.new_code_cell(
            "counts = {}\nfor order in acf_inputs['orders']:\n"
            "    if not order['test'] and start_date <= order['ordered_at'] < end_date:\n"
            "        channel = order['channel']\n        counts[channel] = counts.get(channel, 0) + 1\n"
            "rows = [{'channel': channel, 'orders': count} for channel, count in sorted(counts.items())]")])
    notebook.cells[1].outputs = [nbformat.v4.new_output("stream", text="STALE REFERENCE: orders=999999")]
    nbformat.write(notebook, source)
    case = {"parameters": {"start_date": "2026-09-01", "end_date": "2026-10-01"},
            "as_of": "2026-10-01", "input_snapshot": "fictional-orders-v1", "inputs": {"orders": orders},
            "timezone": "UTC", "random_seed": 42, "output": "rows", "key_columns": ["channel"],
            "tolerance": {"absolute": 0}}
    print(f"test_notebooks: live synthetic evidence retained at {room}", flush=True)
    executor = [sys.executable, str(ROOT / "tests/fixtures/notebook_ai_executor.py")]
    directory, report = verify(root, source, "eligible-orders", "How many eligible orders occurred by channel in the selected date window?", case,
        reference_command=[sys.executable, str(ROOT / "scripts/notebook_reference.py"),
                           "--read-only-environment", "--immutable-input"],
        answer_command=executor, judge_command=executor)
    print(json.dumps({"status": report["status"], "category": report["category"], "report": str(directory / "comparison.json")}))
    assert report["status"] == "pass", report["category"]
    assert report["human_approved"] is False and not (root / "evals/seeds").exists()
    request = json.loads((directory / "answer/request.json").read_text())
    assert "STALE REFERENCE" not in json.dumps(request) and str(source) not in json.dumps(request)
    receipt = json.loads((directory / "answer/receipt.json").read_text())
    assert sorted(receipt["rows"], key=lambda r: r["channel"]) == [
        {"channel": "store", "orders": 3}, {"channel": "web", "orders": 2}]
    executed = nbformat.read(directory / "reference/executed.ipynb", as_version=4)
    assert all(cell.execution_count for cell in executed.cells if cell.cell_type == "code")
    print("test_notebooks: live AI-derived SQL matches fresh reference execution; no human confirmation claimed")
