"""Golden behavior test for scripts/dbt_extract.py — stdlib only, no pytest dep.

The synthetic fixture covers what veritas_dbt lacks — accepted_values,
relationships, a dbt_utils composite-grain test, a custom (unmappable) test, and an
exposure — so every mapping branch and the degradation logic are exercised.

Run: python3 tests/test_dbt_extract.py   (exit 0 = pass)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dbt_extract  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "mini_manifest.json"


def _model(f, name):
    return next(m for m in f["models"] if m["name"] == name)


def run():
    f = dbt_extract.from_manifest(json.loads(FIXTURE.read_text()))

    # metadata
    assert f["source"] == "manifest"
    assert "v11" in f["dbt_schema_version"]
    assert f["dbt_version"] == "1.7.0"
    assert f["compiled_sql"] is True  # fct_orders has compiled_code

    # models present and sorted
    names = [m["name"] for m in f["models"]]
    assert names == sorted(names) == ["dim_customer", "fct_orders", "stg_orders"], names

    fct = _model(f, "fct_orders")
    # real warehouse table + model-only, sorted dependency graph (source dep dropped)
    assert fct["relation"] == "DB.MART.FCT_ORDERS"
    assert fct["depends_on"] == ["dim_customer", "stg_orders"], fct["depends_on"]

    # grain hints: column-unique and dbt_utils composite (namespace stripped)
    assert fct["grain_hint"] == ["order_id"]
    assert _model(f, "dim_customer")["grain_hint"] == ["email + region"]

    # test mapping by type
    by_type = {t["type"]: t for t in fct["tests"]}
    assert by_type["accepted_values"]["kwargs"]["values"] == ["new", "shipped", "cancelled"]
    assert by_type["relationships"]["kwargs"] == {"to": "ref('dim_customer')", "field": "customer_id"}
    assert "not_null" in by_type

    # custom / unmappable test is skipped
    all_types = {t["type"] for m in f["models"] for t in m["tests"]}
    assert "orphaned_records_last_3_months" not in all_types

    # exposure parsed (url + flattened owner + model-only depends_on)
    assert len(f["exposures"]) == 1
    exp = f["exposures"][0]
    assert exp["url"] == "https://bi.example.com/orders"
    assert exp["owner"] == "rev-ops"
    assert exp["depends_on"] == ["fct_orders"]

    # all artifact types present in fixture → nothing unavailable
    assert f["unavailable"] == [], f["unavailable"]

    # coverage counts
    assert f["coverage"] == {
        "models": 3,
        "with_description": 3,
        "with_column_descriptions": 2,
        "with_grain_evidence": 2,
    }, f["coverage"]

    # deterministic
    again = dbt_extract.from_manifest(json.loads(FIXTURE.read_text()))
    assert json.dumps(f, sort_keys=True) == json.dumps(again, sort_keys=True)

    print("test_dbt_extract: all assertions passed")


if __name__ == "__main__":
    run()
