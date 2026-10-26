#!/usr/bin/env python3
"""Customer regression protocol against a synthetic SQLite execution adapter."""
from copy import deepcopy
import json
import importlib.util
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime.regression import run_regression
from acf_runtime.loader import read_yaml, load_context
from acf_runtime.verified import VerifiedSQL
from eval_harness.regression import read_only_sql
from acf_fixtures import context, metric, seed, write

EXECUTOR = r'''
import hashlib, json, sqlite3, sys
from pathlib import Path
r = json.load(sys.stdin)
assert 'expected' not in r and 'value' not in r
mode = sys.argv[1]
if r['role'] == 'judge':
    print(json.dumps({'request_id': r['request_id'], 'status': 'ok', 'verdict': {'passed': True}}))
    sys.exit()
if mode == 'unsupported':
    print(json.dumps({'request_id': r['request_id'], 'status': 'skipped', 'message': 'PRIVATE_RESULT'}))
    sys.exit()
connection = sqlite3.connect(':memory:')
connection.execute('CREATE TABLE orders (test INTEGER)')
connection.executemany('INSERT INTO orders VALUES (?)', [(0,), (1,), (0,)])
connection.execute('PRAGMA query_only = ON')
raw = Path(r['query_path']).read_bytes()
cursor = connection.execute(raw.decode(), r['parameters'])
columns = [c[0] for c in cursor.description]
rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
receipt = {'status': 'ok', 'request_id': r['request_id'], 'executed': True, 'read_only': True,
    'query_hash': 'sha256:' + hashlib.sha256(raw).hexdigest(), 'warehouse': r['warehouse'],
    'parameters_hash': r['parameters_hash'], 'as_of': r['as_of'], 'historical_snapshot': True,
    'rows': rows, 'columns': columns}
if mode == 'mismatch':
    rows[0][columns[0]] += 1
if mode == 'today':
    receipt['historical_snapshot'] = False
if mode == 'unbound':
    receipt['parameters_hash'] = 'other'
if mode == 'no-evidence':
    receipt['executed'] = False
print(json.dumps(receipt))
'''


def run():
    for sql in ("SELECT 1", "WITH x AS (SELECT 1 AS n) SELECT n FROM x", "SELECT 1 UNION ALL SELECT 2"):
        assert read_only_sql(sql, "sqlite") is None
    for sql in ("DELETE FROM orders", "SELECT 1; DROP TABLE orders", "CALL mutate()", "SELECT * INTO new_table FROM orders",
                "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x", "SELECT * FROM orders FOR UPDATE"):
        assert read_only_sql(sql, "postgres") is not None, sql
    assert read_only_sql("SELECT <period_start>", "sqlite") == "unbound_sql_placeholder"
    with TemporaryDirectory() as temp:
        root = Path(temp) / "context"; context(root)
        config = read_yaml(root / "context.config.yaml"); config["warehouse"] = "sqlite"
        write(root, "context.config.yaml", config)
        write(root, "domains/sales/metrics/orders.yaml", metric())
        record = seed(expected={"kind": "value_at_snapshot", "value": 2, "as_of": "2026-10-01"},
                      verified_query_file="evals/verified/orders.sql", provenance="dashboard")
        seed_path = write(root, "evals/seeds/orders.seed.yaml", record)
        query = "SELECT COUNT(*) AS orders FROM orders WHERE test = 0 -- PRIVATE_QUERY"
        VerifiedSQL(root).capture(record["verified_query_file"], query.encode())
        executor = Path(temp) / "execute.py"; executor.write_text(EXECUTOR)
        def check(mode="ok"):
            return run_regression(root, executor=[sys.executable, str(executor), mode])
        directory, report = check()
        assert report["results"] == [{"seed_id": "seed:orders.seed.yaml", "status": "pass", "category": "checks_passed"}], report
        assert "PRIVATE" not in json.dumps(report) and "rows" not in json.dumps(report)
        request = json.loads((directory / "seed-0/execute/request.json").read_text())
        assert not Path(request["query_path"]).exists()  # always cleaned temporary plaintext
        assert (root / record["verified_query_file"]).read_text() == query
        spec = importlib.util.spec_from_file_location("coverage_ci", ROOT / ".ci/coverage.py")
        coverage = importlib.util.module_from_spec(spec); spec.loader.exec_module(coverage)
        registry = load_context(root); current = registry.seed_records()[0]
        checked = json.loads((directory / "evidence.json").read_text())[current["id"]]
        coverage_result = coverage.evidence(root, current, registry.config, checked=checked, registry=registry)
        assert coverage_result["state"] == "checked_pass" and coverage_result["verified"]
        plain = root / record["verified_query_file"]
        plain.write_text(query + "\n")
        stale = coverage.evidence(root, current, registry.config, checked=checked, registry=registry)
        assert stale["state"] == "stale_verification" and not stale["verified"]
        plain.write_text(query)
        assert check("mismatch")[1]["results"][0]["status"] == "fail"
        for mode, category in (("today", "historical_snapshot_unavailable"), ("unbound", "execution_binding_mismatch"),
                               ("no-evidence", "execution_not_attested"), ("unsupported", "executor_reported_skipped")):
            row = check(mode)[1]["results"][0]
            assert row["status"] == "skipped" and row["category"] == category, row
        assert run_regression(root)[1]["results"][0]["category"] == "executor_unconfigured"
        # Dangerous SQL is rejected before customer execution and still cleaned up.
        VerifiedSQL(root).capture(record["verified_query_file"], b"DELETE FROM orders", overwrite=True)
        assert check()[1]["results"][0]["category"] == "sql_not_read_only"
        assert not list((root / "evals/verified").glob(".regression-*"))
        VerifiedSQL(root).capture(record["verified_query_file"], query.encode(), overwrite=True)
        # Cross-warehouse dependencies never silently use the repo default.
        config["lineage_sources"].append({"id": "other", "type": "dbt", "warehouse": "bigquery"})
        write(root, "context.config.yaml", config)
        composite = metric(lineage=[{"source": "dbt", "models": ["orders"]}, {"source": "other", "models": ["orders"]}])
        write(root, "domains/sales/metrics/orders.yaml", composite)
        assert check()[1]["results"][0]["category"] == "cross_warehouse_unsupported"
        write(root, "domains/sales/metrics/orders.yaml", metric(parameters=[{"name": "threshold"}]))
        assert check()[1]["results"][0]["category"] == "parameter_bindings_unresolved"
        write(root, "domains/sales/metrics/orders.yaml", metric())
        # Shape checks without an explicit judge are partial, not numeric proof.
        shape = {**record, "expected": {"kind": "sql_shape", "must_include": ["test = 0"]}}
        write(root, seed_path.relative_to(root), shape)
        registry = load_context(root)
        availability = coverage.evidence(root, registry.seed_records()[0], registry.config)
        assert availability["state"] == "approved_query_available" and not availability["verified"]
        assert check()[1]["results"][0]["category"] == "grading_incomplete"
        judged = run_regression(root, executor=[sys.executable, str(executor), "ok"],
                                judge=[sys.executable, str(executor), "ok"])[1]
        assert judged["results"][0]["status"] == "pass"
        # CLI without an executor explicitly reports skipped and exits 3.
        result = subprocess.run([sys.executable, str(ROOT / "scripts/regress.py"), "--root", str(root)], capture_output=True, text=True)
        assert result.returncode == 3 and "executor_unconfigured" in result.stdout
        assert "PRIVATE" not in result.stdout + result.stderr
    print("test_regression: OK")


if __name__ == "__main__":
    run()
