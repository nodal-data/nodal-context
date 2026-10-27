#!/usr/bin/env python3
"""Static-import isolation and independent notebook verification protocol tests.

All inputs are synthetic. --kernel uses no agent/network/warehouse. --live-ai
explicitly runs the model and a kernel. Normal direct runs remain offline.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime.loader import load_context, read_method
from acf_runtime.notebooks import draft_notebook, render_method
from acf_runtime.notebook_verification import verify, confirm
from eval_harness.execution import invoke, strict_json
from acf_fixtures import context, metric, method, write, METHOD_BODY


EXECUTOR = r'''
import json, sys, uuid
r = json.load(sys.stdin)
mode = sys.argv[1]
if r['role'] == 'judge':
    obligation = r['obligations']
    if obligation['kind'] == 'method_decisions':
        ok = ('not row["test"]' in r['evidence'].get('python', '') or
              'WHERE test = 0' in r['evidence'].get('sql', ''))
    elif obligation['kind'] == 'method_disclosures':
        ok = 'window' in r['evidence']['explanation']
    else:
        ok = False
    print(json.dumps({'request_id': r['request_id'], 'status': 'ok', 'verdict': {'passed': ok, 'reason': 'synthetic independent judge'}}))
    sys.exit()
if r['role'] == 'answer':
    assert 'notebook' not in r and 'source_hash' not in r and 'expected' not in r
    assert 'REFERENCE_ONLY' not in json.dumps(r)
    assert 'secret-notebook.ipynb' not in json.dumps(r)
code = 'rows = [{"channel": "web", "orders": sum(1 for row in source if not row["test"]), "population": len(source)}]'
namespace = {'source': r['inputs']['orders']}
exec(code, namespace)
rows = namespace['rows']
sql = ''
if mode == 'sql' and r['role'] == 'answer':
    import sqlite3
    database = sqlite3.connect(':memory:')
    database.execute('CREATE TABLE orders (test INTEGER)')
    database.executemany('INSERT INTO orders VALUES (?)', [(int(row['test']),) for row in r['inputs']['orders']])
    database.execute('PRAGMA query_only = ON')
    sql = "SELECT 'web' AS channel, COUNT(*) AS orders, (SELECT COUNT(*) FROM orders) AS population FROM orders WHERE test = 0"
    cursor = database.execute(sql)
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, values)) for values in cursor.fetchall()]
if mode == 'mismatch' and r['role'] == 'answer':
    rows[0]['orders'] += 1
if mode == 'duplicate':
    rows = rows + rows
receipt = {'request_id': r['request_id'], 'status': 'ok', 'executed': True,
    'read_only': True, 'fresh_session': True, 'immutable_input': True, 'session_id': uuid.uuid4().hex,
    'input_fingerprint': r['input_fingerprint'], 'context_hash': r['context_hash'], 'as_of': r['as_of'],
    'environment': {'python': sys.version.split()[0]}, 'rows': rows, 'columns': list(rows[0]),
    'answer': {'outcome': 'answer', 'python': code, 'explanation': 'window bound from parameters'}}
if sql:
    receipt['answer']['sql'] = sql
    receipt['answer'].pop('python')
if r['role'] == 'reference':
    receipt['source_hash'] = r['source_hash']
else:
    receipt['reference_access'] = False
if mode == 'shared-session':
    receipt['session_id'] = 'same-session'
if mode == 'missing-evidence':
    del receipt['executed']
if mode == 'mutable':
    receipt['immutable_input'] = False
if mode == 'wrong-input':
    receipt['input_fingerprint'] = 'wrong'
if mode == 'bad-disclosure':
    receipt['answer']['explanation'] = 'done'
if mode == 'claimed-only':
    receipt['answer'].pop('python')
if mode == 'invalid-json':
    print('not JSON')
else:
    print(json.dumps(receipt))
'''


def assert_raises(fn):
    try:
        fn()
    except (ValueError, OSError):
        return
    raise AssertionError("expected operation to refuse")


def run_tests(kernel=False):
    if importlib.util.find_spec("nbformat") is None or importlib.util.find_spec("sqlglot") is None:
        raise AssertionError("notebook tests require optional nbformat and sqlglot dependencies")
    import nbformat
    from fixtures.notebook_ai_executor import answer as ai_answer, execute_sql
    request = {"role": "answer", "request_id": "test", "context": {}, "parameters": {},
               "as_of": "2026-10-01", "timezone": "UTC", "resolved_metrics": [],
               "question": "Orders?", "input_fingerprint": "test", "context_hash": "test",
               "inputs": {"orders": [{"order_id": 1, "channel": "web", "ordered_at": "2026-09-01", "test": False}]}}
    prompts = []
    def model_double(question, context):
        prompts.append((question, context))
        return {"outcome": "answer", "sql": "SELECT channel, COUNT(*) AS orders FROM orders WHERE test = 0 GROUP BY channel", "python": ""}
    receipt = ai_answer(request, model_double)
    assert receipt["rows"] == [{"channel": "web", "orders": 1}] and receipt["executed"]
    assert "inputs" not in json.loads(prompts[0][1])  # no reference or computed answer sent to model
    assert_raises(lambda: ai_answer({**request, "expected": []}, model_double))
    assert len(prompts) == 1
    import sqlite3
    for sql in ("DROP TABLE orders", "ATTACH DATABASE '/tmp/forbidden' AS other", "SELECT load_extension('absent')", "SELECT * FROM sqlite_master"):
        try:
            execute_sql(sql, request["inputs"]["orders"])
        except (ValueError, sqlite3.DatabaseError):
            pass
        else:
            raise AssertionError("synthetic executor accepted forbidden SQL: " + sql)
    from scripts.notebook_reference import preflight, bind_parameters
    with TemporaryDirectory() as temp:
        folder = Path(temp)
        root = folder / "context"
        context(root)
        write(root, "domains/sales/metrics/orders.yaml", metric())
        registry = load_context(root)
        source = folder / "secret-notebook.ipynb"
        marker = folder / "must-not-exist"
        book = nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell("Revenue was 999999. password=PRIVATE. REFERENCE_ONLY"),
            nbformat.v4.new_code_cell("window = 30\npassword = 'PRIVATE'", metadata={"tags": ["parameters"]}),
            nbformat.v4.new_code_cell('df = pd.read_sql("SELECT channel, COUNT(*) AS orders FROM orders WHERE test = FALSE GROUP BY channel", conn)'),
            nbformat.v4.new_code_cell("assert returned <= cohort_size"),
            nbformat.v4.new_code_cell(f"open({str(marker)!r}, 'w').write('should not execute')")])
        book.cells[2].outputs = [nbformat.v4.new_output("stream", text="PRIVATE saved results 999999")]
        nbformat.write(book, source)
        assert_raises(lambda: preflight(book))
        assert not marker.exists()
        unsafe_parameters = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(
            "window = fetch_remote()", metadata={"tags": ["parameters"]})])
        assert_raises(lambda: bind_parameters(unsafe_parameters, {"window": 30}))
        data, body, report = draft_notebook(source, name="imported-orders", domain="sales", registry=registry)
        rendered = render_method(data, body)
        assert not marker.exists()
        assert "status" not in data and "approver" not in data
        assert all(d["without_this"] == "" for d in data["decisions"])
        assert [p["name"] for p in data["parameters"]] == ["window"]
        assert data["metrics"] == ["orders"], report
        assert data["checks"] == ["returned <= cohort_size for every row"]
        assert "PRIVATE" not in rendered and "999999" not in rendered and "SELECT" not in rendered
        assert data["provenance"]["ref"].startswith("sha256:")
        write(root, "methods/imported-orders.md", data, body)
        loaded = load_context(root)
        assert not loaded.errors, loaded.errors
        assert any(d.code == "decision.rationale" for d in loaded.diagnostics)
        # A filter mismatch is a review candidate, never an exact reference.
        book.cells[2].source = book.cells[2].source.replace("FALSE", "TRUE")
        nbformat.write(book, source)
        drift, _, drift_report = draft_notebook(source, name="drift", domain="sales", registry=registry)
        assert not drift["metrics"] and drift_report["metric_candidates"][0]["match"] == "possible_drift"
        dynamic = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(
            'query = "SELECT COUNT(*) AS orders FROM orders WHERE test = FALSE"\ndf = pd.read_sql(query, conn)\ndf')])
        alternate = folder / "literal-query.ipynb"
        nbformat.write(dynamic, alternate)
        literal_draft, _, literal_report = draft_notebook(alternate, name="literal", domain="sales", registry=registry)
        assert literal_draft["metrics"] == ["orders"]
        assert "output" in literal_report["cells"][0]["classes"]
        # CLI authoring requires a working branch; it still refuses overwrite.
        subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(root), 'checkout', '-qb', 'notebook-proposal'], check=True)
        # CLI refuses to replace the existing authored draft.
        command = [sys.executable, str(ROOT / "scripts/import_notebook.py"), str(source), "--root", str(root),
                   "--name", "imported-orders", "--domain", "sales"]
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 1 and "already exists" in result.stderr
        assert not marker.exists()

        reviewed = method()
        reviewed["output"]["columns"] = ["channel", "orders", "population"]
        reviewed["checks"] = ["orders <= population for every row"]
        reviewed["provenance"] = {"kind": "notebook", "path": "secret-notebook.ipynb", "ref": "source-revision"}
        write(root, "methods/repeat.md", reviewed, METHOD_BODY)
        case = {"parameters": {"window": "last_month"}, "as_of": "2026-10-01", "input_snapshot": "synthetic-v1",
                "inputs": {"orders": [{"test": False}, {"test": True}]}, "timezone": "UTC", "random_seed": 42,
                "output": "rows", "key_columns": ["channel"], "tolerance": {"absolute": 0}}
        executor = folder / "executor.py"
        executor.write_text(EXECUTOR)
        def run(mode="ok", reference=None, judge=True):
            return verify(root, source, "repeat", "Eligible orders by channel?", case,
                reference_command=reference or [sys.executable, str(executor), mode],
                answer_command=[sys.executable, str(executor), mode],
                judge_command=[sys.executable, str(executor), "ok"] if judge else None)
        directory, comparison = run()
        assert comparison["status"] == "pass", comparison
        assert not comparison["human_approved"]
        assert not (root / "evals/seeds").exists()
        request = strict_json((directory / "answer/request.json").read_text())
        assert "provenance" not in json.dumps(request)
        seed = confirm(root, directory / "comparison.json", seed_name="notebook-orders",
                       approver="fictional-test-owner", confirmed_at="2026-10-01")
        assert seed.is_file() and not load_context(root).errors
        from acf_runtime.notebook_verification import checked_evidence
        current = load_context(root)
        record = next(s for s in current.seed_records() if s["path"] == "evals/seeds/notebook-orders.seed.yaml")
        relative_report = str((directory / "comparison.json").relative_to(root.resolve()))
        assert checked_evidence(root, record, current, relative_report)["verified"]
        approval_path = directory / "approval-notebook-orders.json"
        private_approval = folder / "external-approval.json"
        approval_bytes = approval_path.read_bytes()
        approval_path.rename(private_approval)
        approval_path.symlink_to(private_approval)
        assert checked_evidence(root, record, current, relative_report)["state"] == "notebook_evidence_unavailable"
        assert private_approval.read_bytes() == approval_bytes
        approval_path.unlink()
        private_approval.rename(approval_path)
        assert checked_evidence(root, record, current, relative_report)["verified"]
        notebook_before, seed_before = source.read_bytes(), seed.read_bytes()
        source.write_bytes(notebook_before + b"\n")
        stale = checked_evidence(root, record, current, relative_report)
        assert not stale["verified"] and stale["stale_reasons"] == ["notebook_source_changed"]
        assert seed.read_bytes() == seed_before
        command = [sys.executable, str(ROOT / ".ci/coverage.py"), str(root), "--json",
                   "--notebook-run", "notebook-orders.seed.yaml=" + relative_report]
        covered = subprocess.run(command, capture_output=True, text=True)
        assert covered.returncode == 0, covered.stderr
        coverage = json.loads(covered.stdout)
        snapshots = coverage["targets"]["method:repeat"]["verification"]
        assert any(row["state"] == "stale_verification" and not row["verified"] for row in snapshots)
        assert str(source) not in covered.stdout  # private notebook locator is not a public report field
        source.write_bytes(notebook_before)
        missing = source.with_suffix(".temporarily-missing")
        source.rename(missing)
        assert checked_evidence(root, record, current, relative_report)["state"] == "notebook_evidence_unavailable"
        missing.rename(source)
        original_method = (root / "methods/repeat.md").read_bytes()
        edited = deepcopy(reviewed); edited["description"] = "Changed definition after confirmation"
        write(root, "methods/repeat.md", edited, METHOD_BODY)
        changed = load_context(root)
        assert not checked_evidence(root, record, changed, relative_report)["verified"]
        (root / "methods/repeat.md").write_bytes(original_method)
        assert checked_evidence(root, record, load_context(root), relative_report)["verified"]
        assert_raises(lambda: confirm(root, directory / "comparison.json", seed_name="notebook-orders",
                       approver="fictional-test-owner", confirmed_at="2026-10-01"))
        sql_directory, sql_comparison = run("sql")
        assert sql_comparison["status"] == "pass", sql_comparison
        sql_receipt = strict_json((sql_directory / "answer/receipt.json").read_text())
        approved_sql = folder / "approved.sql"
        approved_sql.write_text(sql_receipt["answer"]["sql"])
        # Publication failure rolls back this attempt's seed and SQL so the
        # same name can be retried; pre-existing user artifacts are untouched.
        with patch("acf_runtime.notebook_verification.private_json", side_effect=OSError("receipt unavailable")):
            try:
                confirm(root, sql_directory / "comparison.json", seed_name="sql-method",
                        approver="fictional-test-owner", confirmed_at="2026-10-01", approved_sql=approved_sql)
            except OSError:
                pass
            else:
                raise AssertionError("receipt failure not exercised")
        assert not (root / "evals/verified/sql-method.sql").exists()
        assert not (root / "evals/seeds/sql-method.seed.yaml").exists()
        sql_seed = confirm(root, sql_directory / "comparison.json", seed_name="sql-method",
                          approver="fictional-test-owner", confirmed_at="2026-10-01", approved_sql=approved_sql)
        assert "verified_query_file: evals/verified/sql-method.sql" in sql_seed.read_text()
        approval = strict_json((sql_directory / "approval-sql-method.json").read_text())
        assert approval["sql_publication"]["status"] == "local_only"
        approved_sql.write_text("SELECT 'changed after verification'")
        assert_raises(lambda: confirm(root, sql_directory / "comparison.json", seed_name="changed-sql",
                       approver="fictional-test-owner", confirmed_at="2026-10-01", approved_sql=approved_sql))
        assert not (root / "evals/verified/changed-sql.sql").exists()
        assert run("mismatch")[1]["status"] == "fail"
        assert run("duplicate")[1]["status"] == "blocked"
        for mode in ("shared-session", "missing-evidence", "mutable", "wrong-input", "invalid-json"):
            assert run(mode)[1]["status"] == "blocked", mode
        for mode in ("bad-disclosure", "claimed-only"):
            assert run(mode)[1]["status"] == "fail", mode
        assert run(judge=False)[1]["status"] == "skipped"
        assert verify(root, source, "repeat", "Question?", case)[1]["status"] == "skipped"
        assert_raises(lambda: verify(root, source, "repeat", "Question?", case, answer_command=[]))
        # Timeout cleanup includes child processes, not just the executor parent.
        late_marker = folder / "late-child-output"
        child = "import time; from pathlib import Path; time.sleep(1); Path(" + repr(str(late_marker)) + ").write_text('leaked')"
        parent = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', " + repr(child) + "]); time.sleep(10)"
        timed = invoke([sys.executable, "-c", parent], {"role": "test"}, folder / "timeout-test", timeout=0.2)
        assert timed["status"] == "blocked" and timed["category"] == "executor_timeout"
        time.sleep(1.1)
        assert not late_marker.exists(), "timeout left a child process running"
        # Changing the method invalidates a previous comparison before promotion.
        reviewed["description"] = "Changed interpretation"
        write(root, "methods/repeat.md", reviewed, METHOD_BODY)
        assert_raises(lambda: confirm(root, directory / "comparison.json", seed_name="stale-method",
                       approver="fictional-test-owner", confirmed_at="2026-10-01"))
        reviewed["description"] = method()["description"]
        write(root, "methods/repeat.md", reviewed, METHOD_BODY)
        source.write_text(source.read_text() + "\n")
        assert_raises(lambda: confirm(root, directory / "comparison.json", seed_name="stale-source",
                       approver="fictional-test-owner", confirmed_at="2026-10-01"))

        if kernel:
            # A real new Jupyter kernel reruns a synthetic notebook. This tests the
            # reference executor; the answer/judge are deterministic test doubles.
            live = nbformat.v4.new_notebook(cells=[
                nbformat.v4.new_code_cell("window = 'default'", metadata={"tags": ["parameters"]}),
                nbformat.v4.new_code_cell('rows = [{"channel": "web", "orders": len([x for x in acf_inputs["orders"] if x["test"] is False]), "population": len(acf_inputs["orders"])}]')])
            # Deliberately stale saved output must not be used.
            live.cells[1].outputs = [nbformat.v4.new_output("stream", text="orders=999999")]
            nbformat.write(live, source)
            reference = [sys.executable, str(ROOT / "scripts/notebook_reference.py"),
                         "--read-only-environment", "--immutable-input"]
            live_dir, live_result = run(reference=reference)
            assert live_result["status"] == "pass", (live_result, (live_dir / "reference/diagnostics.json").read_text())
            executed = nbformat.read(live_dir / "reference/executed.ipynb", as_version=4)
            assert "last_month" in executed.cells[1].source
            assert live_result["expected"]["value"][0]["orders"] == 1
            assert all(c.execution_count for c in executed.cells if c.cell_type == "code")
            print("test_notebooks: actual synthetic fresh-kernel reference rerun passed")
    print("test_notebooks: OK")


if __name__ == "__main__":
    if "--live-ai" in sys.argv:
        from notebook_live import run
        run()
    else:
        run_tests("--kernel" in sys.argv)
