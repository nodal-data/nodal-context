"""Typed structural identity, ambiguity, method defaults and holdout isolation."""
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval_harness.matching import normalize, relation, match_question


def run():
    definitions = {
        "metric:sales.orders": {"kind": "metric", "domain": "sales", "name": "orders", "aliases": ["purchases"],
            "grain": "order", "dimensions": ["channel", "date"], "defined": True, "effective_status": "confirmed"},
        "metric:sales.new_orders": {"kind": "metric", "domain": "sales", "name": "new_orders",
            "grain": "order", "dimensions": ["channel"], "defined": True, "effective_status": "confirmed"},
        "method:retention": {"kind": "method", "domain": "sales", "name": "retention", "defined": True,
            "effective_status": "confirmed", "parameters": [{"name": "window"}, {"name": "anchor", "default": "activity"}],
            "metrics": ["metric:sales.orders", "metric:sales.new_orders"]},
    }
    def norm(ir):
        return normalize(ir, "sales", definitions)
    f = {"any_of": [{"field": "channel", "op": "=", "value": "direct"}, {"field": "channel", "op": "is_null"}], "reason": "A"}
    a = {"metric": "orders", "dimensions": ["date", "channel", "date"], "filters": [f], "time_window": "last_month"}
    b = {"metric": "sales.orders", "dimensions": ["channel", "date"], "filters": [{"any_of": list(reversed(f["any_of"])), "reason": "B"}], "time_window": "last_quarter"}
    assert relation(norm(a), norm(b)) == "equivalent"
    b["filters"] = [{"all_of": f["any_of"]}]
    assert relation(norm(a), norm(b)) == "same_metric_new_slice"
    one = {"metric": "orders", "filters": [{"field": "x", "op": "=", "value": 1}]}
    string = deepcopy(one); string["filters"][0]["value"] = "1"
    assert relation(norm(one), norm(string)) == "same_metric_new_slice"
    unknown = norm({"metric": "missing"})
    assert unknown.state == "unresolved"
    definitions["metric:sales.new_orders"]["aliases"] = ["purchases"]
    assert norm({"metric": "purchases"}).state == "ambiguous"
    assert norm({"metric": "sales.orders"}).state == "resolved"
    assert "dimension_not_allowed" in norm({"metric": "orders", "dimensions": ["postal_code"]}).blockers
    m1 = {"method": "retention", "metrics": ["orders"], "parameters": {"window": "last_month"}, "dimensions": ["channel"]}
    m2 = deepcopy(m1); m2["parameters"].update(window="last_year", anchor="activity")
    assert relation(norm(m1), norm(m2)) == "equivalent"
    m2["metrics"] = ["new_orders"]
    assert relation(norm(m1), norm(m2)) == "same_metric_new_slice"
    m2["parameters"]["undeclared"] = True
    assert norm(m2).state == "unresolved"
    seed = {"id": "seed:one", "domain": "sales", "ir": a, "effective_status": "confirmed", "expected": {"kind": "sql_shape", "must_include": ["A"]}}
    assert match_question(a, "sales", definitions, [seed])["relation"] == "equivalent"
    assert not match_question(a, "sales", definitions, [seed], exclude=["seed:one"])["seeds"]
    assert match_question({"parts": [a, {"metric": "missing"}]}, "sales", definitions, [seed])["relation"] == "decomposes"
    assert match_question(a, "sales", definitions, [seed], candidates=["sales.orders", "sales.new_orders"])["relation"] == "ambiguous"
    conflict = deepcopy(seed); conflict["id"] = "seed:two"; conflict["expected"]["must_include"] = ["B"]
    assert "ground_truth_conflict" in match_question(a, "sales", definitions, [seed, conflict])["blockers"]
    different = deepcopy(seed); different["ir"] = {"metric": "new_orders"}
    assert match_question(a, "sales", definitions, [different])["relation"] == "related_only"
    definitions["metric:sales.orders"]["effective_status"] = "draft"
    assert "definition_not_confirmed" in match_question(a, "sales", definitions, [seed])["blockers"]
    # Time is excluded from identity, but unsupported vocabulary is not an
    # equivalent match. This shared path also serves extraction and coverage.
    definitions["metric:sales.orders"]["time_tokens"] = ["last_month", "last_quarter"]
    bad_window = {**a, "time_window": "last_magic_period"}
    result = match_question(bad_window, "sales", definitions, [seed])
    assert result["relation"] == "unresolved" and result["seeds"] == []
    assert "unknown_time_token" in result["unsupported"]
    assert norm(a).state == "resolved"
    definitions["method:retention"]["time_tokens"] = []
    assert norm({**m1, "time_window": "last_month"}).state == "unresolved"
    assert norm(m1).state == "resolved"  # arbitrary method parameters are not time tokens
    # No vocabulary supplied by another adapter preserves format independence.
    assert norm({"metric": "new_orders", "time_window": "custom_window"}).state == "resolved"
    print("test_matching: OK")


if __name__ == "__main__":
    run()
