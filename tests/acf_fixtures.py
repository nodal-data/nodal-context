"""Small, explicitly fictional 0.3 context fixtures for direct tests."""
from copy import deepcopy
from pathlib import Path
import yaml

APPROVAL = {"status": "confirmed", "approver": "fictional-test-owner", "confirmed_at": "2026-10-01"}


def write(root, path, data, body=None):
    target = Path(root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False)
    target.write_text(text if body is None else "---\n" + text + "---\n\n" + body)
    return target


def context(root):
    write(root, "context.config.yaml", {"version": "0.3", "warehouse": "snowflake",
          "lineage_sources": [{"id": "dbt", "type": "dbt"}],
          "time_tokens": {"calendar": ["last_month", "last_quarter"], "fiscal": []},
          "variants": {"max_per_seed": 2}, "verified_sql": {"encryption": "none"}})
    domain(root, "sales")


def domain(root, name):
    write(root, f"domains/{name}/domain.yaml", {"name": name, "summary": "Fictional fixture",
          "status": "confirmed", "grain": "order", "lineage": [{"source": "dbt", "models": ["orders"]}]})


def metric(name="orders", **changes):
    value = {"name": name, "definition": "Fictional eligible order count", **APPROVAL,
             "grain": "order", "lineage": [{"source": "dbt", "models": ["orders"]}],
             "temporal_kind": "flow", "expression": {"measure": "COUNT(*)",
             "mandatory_filters": [{"field": "test", "op": "=", "value": False, "reason": "Exclude test orders."}],
             "allowed_dimensions": ["channel", "date"]}}
    value.update(deepcopy(changes))
    return value


def method():
    return {"name": "repeat", "kind": "method", **APPROVAL, "domain": "sales",
            "aliases": ["repeat purchases"], "description": "Fictional repeat analysis",
            "metrics": ["orders"], "lineage": "inherit",
            "parameters": [{"name": "window", "note": "Reporting window"}],
            "decisions": [{"id": "identity", "rule": "Use canonical identity in <window>.",
                           "without_this": "Aliases double count customers."}],
            "output": {"grain": "channel", "columns": ["channel", "orders"],
                       "dimensions": ["channel"], "must_state": ["window used"]},
            "checks": ["Orders reconcile with the underlying metric."]}


METHOD_BODY = "## When to use\n\nRepeat questions.\n\n## Procedure\n\n1. Count canonical identities in <window> (`identity`).\n"


def seed(**changes):
    value = {"question": "Orders by channel last month?", "intent": "Count eligible orders",
             "domain": "sales", **APPROVAL, "provenance": "interview",
             "ir": {"metric": "orders", "dimensions": ["channel"], "time_window": "last_month"},
             "expected": {"kind": "sql_shape", "must_include": ["Exclude test orders"]}}
    value.update(deepcopy(changes))
    return value
