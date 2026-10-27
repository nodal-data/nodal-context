"""Opt-in synthetic notebook acceptance executor; never a customer SQL runner.

The model receives only stdin's answer context. It has no tools or filesystem
access. Its SQL runs in a fresh in-memory SQLite database with a restrictive
authorizer; generated Python is never executed. Ordinary tests inject a model
double. The CLI makes real model calls using the existing BYO-key client.
"""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from eval_harness import client
from eval_harness.regression import read_only_sql


def execute_sql(sql, orders):
    problem = read_only_sql(sql, "sqlite")
    if problem:
        raise ValueError(problem)
    with closing(sqlite3.connect(":memory:")) as database:
        database.execute("CREATE TABLE orders (order_id INTEGER, channel TEXT, ordered_at TEXT, test INTEGER)")
        database.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", [
            (row["order_id"], row["channel"], row["ordered_at"], row["test"]) for row in orders])
        database.commit()
        database.execute("PRAGMA query_only = ON")

        def authorize(action, arg1, arg2, _database, _trigger):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and arg1 == "orders":
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and arg2.lower() in {
                    "count", "sum", "min", "max", "avg", "coalesce", "date", "datetime", "strftime"}:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        database.set_authorizer(authorize)
        # Bound compute and output even for syntactically read-only SQL.
        steps = 0
        def budget():
            nonlocal steps
            steps += 1
            return int(steps > 1000)
        database.set_progress_handler(budget, 1000)
        cursor = database.execute(sql)
        columns = [column[0] for column in cursor.description]
        values = cursor.fetchmany(1001)
        if len(values) > 1000 or len(columns) != len(set(columns)):
            raise ValueError("unbounded result or duplicate output columns")
        return columns, [dict(zip(columns, row)) for row in values]


def answer(request, generate=None):
    if request.get("role") != "answer" or any(key in request for key in (
            "notebook", "source_hash", "expected", "reference", "output")):
        raise ValueError("answer request must be independent of the reference")
    generate = generate or client.generate
    context = {
        "context": request["context"], "parameters": request["parameters"],
        "as_of": request["as_of"], "timezone": request["timezone"],
        "resolved_metrics": request["resolved_metrics"],
        "execution_contract": "SQLite, one SELECT. Table orders(order_id INTEGER, channel TEXT, ordered_at TEXT, test INTEGER). Dates use YYYY-MM-DD; booleans use 0/1. Return SQL with bound literal parameter values, no Python. Include required method disclosures. No tools or reference outputs are available.",
    }
    proposal = generate(request["question"], json.dumps(context))
    if proposal.get("outcome") != "answer" or not proposal.get("sql") or proposal.get("python"):
        raise ValueError("model did not propose executable SQL")
    columns, rows = execute_sql(proposal["sql"], request["inputs"]["orders"])
    return {"request_id": request["request_id"], "status": "ok", "executed": True,
            "read_only": True, "fresh_session": True, "immutable_input": True,
            "session_id": uuid.uuid4().hex, "reference_access": False,
            "input_fingerprint": request["input_fingerprint"], "context_hash": request["context_hash"],
            "as_of": request["as_of"], "environment": {"sqlite": sqlite3.sqlite_version, "model": client.MODEL},
            "columns": columns, "rows": rows, "answer": proposal}


def main():
    request = json.load(sys.stdin)
    if request["role"] == "answer":
        result = answer(request)
    elif request["role"] == "judge":
        result = {"request_id": request["request_id"], "status": "ok",
                  "verdict": client.judge(request["evidence"], request["obligations"])}
    else:
        raise ValueError("unsupported role")
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
