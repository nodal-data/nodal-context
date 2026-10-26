"""Manifest-backed column equivalence, with no guessing across missing/ambiguous lineage."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime import load_context
from acf_runtime.columns import column_evidence
from eval_harness.matching import match_question, normalize
from acf_fixtures import context, metric, method, seed, write, METHOD_BODY


def record(name, columns, package="fixture"):
    return {"resource_type": "model", "name": name, "unique_id": f"model.{package}.{name}",
            "columns": {column: {} for column in columns}}


def run():
    orders = record("orders", ["test", "channel", "date"])
    manifest = {"nodes": {orders["unique_id"]: orders}}
    aliases, ambiguous = column_evidence({"dbt": manifest}, {("dbt", "orders")})
    assert aliases["channel"] == aliases["model.fixture.orders.channel"] == "orders.channel"
    assert not ambiguous
    assert column_evidence({}, {("dbt", "orders")}) == ({}, [])
    assert column_evidence({"dbt": manifest}, {("dbt", "orders"), ("other", "unknown")}) == ({}, [])
    assert column_evidence({"dbt": manifest}, {("dbt", "orders"), ("dbt", "model.fixture.orders")}) == (aliases, [])
    customers = record("customers", ["channel", "customer_id"])
    both = deepcopy(manifest); both["nodes"][customers["unique_id"]] = customers
    multi, ambiguous = column_evidence({"dbt": both}, {("dbt", "orders"), ("dbt", "customers")})
    assert "channel" in ambiguous and "channel" not in multi
    assert multi["orders.channel"] != multi["customers.channel"]
    # Even explicit model names are uncertain when two source warehouses expose them.
    multi, ambiguous = column_evidence({"a": manifest, "b": manifest}, {("a", "orders"), ("b", "orders")})
    assert "orders.channel" in ambiguous and "orders.channel" not in multi
    duplicate = deepcopy(manifest)
    duplicate["nodes"]["model.another.orders"] = record("orders", ["channel"], "another")
    assert column_evidence({"dbt": duplicate}, {("dbt", "orders")}) == ({}, [])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); context(root)
        write(root, "domains/sales/metrics/orders.yaml", metric())
        write(root, "methods/repeat.md", method(), METHOD_BODY)
        s = seed(); s["ir"]["filters"] = [{"any_of": [
            {"field": "channel", "op": "=", "value": "direct"},
            {"field": "channel", "op": "is_null"}]}]
        write(root, "evals/seeds/orders.seed.yaml", s)
        registry = load_context(root, schemas=ROOT / "schemas", manifests={"dbt": manifest})
        assert not registry.errors, registry.errors
        query = deepcopy(s["ir"])
        query["dimensions"] = ["orders.channel", "channel"]
        for child in query["filters"][0]["any_of"]:
            child["field"] = "model.fixture.orders.channel"
        defs = registry.definitions()
        result = match_question(query, "sales", defs, registry.seed_records())
        assert result["relation"] == "equivalent" and not result["blockers"]
        assert result["ir"]["dimensions"] == ["orders.channel"]
        assert all(f["field"] == "orders.channel" for f in result["ir"]["filters"][0]["any_of"])
        assert s["ir"]["dimensions"] == ["channel"]  # never mutate authored records
        no_manifest = load_context(root, schemas=ROOT / "schemas")
        result = match_question(query, "sales", no_manifest.definitions(), no_manifest.seed_records())
        assert result["relation"] != "equivalent" and "dimension_not_allowed" in result["blockers"]
        assert not no_manifest.definitions()["metric:sales.orders"]["column_aliases"]
        method_ir = {"method": "repeat", "metrics": ["orders"], "parameters": {"window": "last_month"},
                     "dimensions": ["orders.channel"]}
        normalized = normalize(method_ir, "sales", defs)
        assert normalized.state == "resolved" and not normalized.blockers
        # Validation uses the same evidence after inherited lineage is complete.
        s["ir"]["dimensions"] = ["orders.channel"]
        write(root, "evals/seeds/orders.seed.yaml", s)
        derived = metric("derived", lineage="inherit", expression={"measure": "metric(orders)",
                         "allowed_dimensions": ["model.fixture.orders.channel"]})
        write(root, "domains/sales/metrics/derived.yaml", derived)
        m = method(); m["output"]["dimensions"] = ["orders.channel"]
        write(root, "methods/repeat.md", m, METHOD_BODY)
        registry = load_context(root, schemas=ROOT / "schemas", manifests={"dbt": manifest})
        assert not registry.errors, [str(d) for d in registry.errors]
        absent = load_context(root, schemas=ROOT / "schemas")
        assert {"dimensions.reference", "dimensions.seed", "dimensions.method"}.issubset({d.code for d in absent.errors})
        alternate = metric("other", lineage=[{"source": "dbt", "models": ["customers"]}],
                           expression={"measure": "COUNT(*)", "allowed_dimensions": ["channel"]})
        write(root, "domains/sales/metrics/other.yaml", alternate)
        m = method(); m["metrics"] = ["orders", "other"]
        write(root, "methods/repeat.md", m, METHOD_BODY)
        registry = load_context(root, schemas=ROOT / "schemas", manifests={"dbt": both})
        assert not registry.errors, [str(d) for d in registry.errors]
        defs = registry.definitions()
        assert "channel" in defs["method:repeat"]["ambiguous_columns"]
        one_branch = normalize({**method_ir, "dimensions": ["channel"]}, "sales", defs)
        assert one_branch.state == "resolved" and not one_branch.blockers
        both_branches = normalize({**method_ir, "metrics": ["orders", "other"], "dimensions": ["channel"]}, "sales", defs)
        assert both_branches.state == "unresolved" and "ambiguous_column:channel" in both_branches.unsupported
        # Same bare field in two lineage models is not proven equivalent, even
        # when both seed and question use that spelling.
        write(root, "domains/sales/metrics/orders.yaml", metric(lineage=[{"source": "dbt", "models": ["orders", "customers"]}]))
        registry = load_context(root, schemas=ROOT / "schemas", manifests={"dbt": both})
        result = match_question(s["ir"], "sales", registry.definitions(), registry.seed_records())
        assert result["relation"] == "unresolved" and "ambiguous_column:channel" in result["unsupported"]
    print("test_column_matching: OK")


if __name__ == "__main__":
    run()
