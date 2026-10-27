"""Method reference dependencies and mechanical authoring rules; no model calls."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime import load_context
from acf_runtime.impact import lineage_impact
from acf_fixtures import context, metric, method, seed, write, METHOD_BODY


def run():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); context(root)
        write(root, "domains/sales/metrics/orders.yaml", metric())
        entities = {"entities": [
            {"name": "canonical-customer", "description": "Fictional identity rule.", "status": "confirmed",
             "lineage": [{"source": "dbt", "models": ["customers"]}]},
            {"name": "other-customer", "description": "Different fictional rule.", "status": "draft"}]}
        write(root, "entities/customers.yaml", entities)
        m = method(); m["decisions"][0]["references"] = ["entities/customers.yaml#canonical-customer"]
        write(root, "methods/repeat.md", m, METHOD_BODY)
        write(root, "evals/seeds/repeat.seed.yaml", seed(ir={"method": "repeat", "metrics": ["orders"],
            "parameters": {"window": "last_month"}}))
        def load():
            return load_context(root, schemas=ROOT / "schemas")
        r = load()
        assert not r.errors, [str(d) for d in r.errors]
        method_node = r.nodes["method:repeat"]
        assert "entity:entities/customers.yaml#canonical-customer" in method_node.dependencies
        assert "entity:entities/customers.yaml#other-customer" not in method_node.dependencies
        assert method_node.effective_status == "confirmed"
        assert ("dbt", "customers") in method_node.lineage
        affected = {item["id"] for item in lineage_impact(r, {("dbt", "customers")})["objects"]}
        assert {"method:repeat", "seed:repeat.seed.yaml"}.issubset(affected)
        entities["entities"][0]["status"] = "draft"
        write(root, "entities/customers.yaml", entities)
        r = load()
        assert r.nodes["method:repeat"].effective_status == "draft"
        assert r.nodes["seed:repeat.seed.yaml"].effective_status == "draft"
        assert r.nodes["method:repeat"].data["status"] == "confirmed"
        entities["entities"][0]["status"] = "confirmed"
        write(root, "entities/customers.yaml", entities)
        m["decisions"][0]["references"] = ["entities/customers.yaml"]
        write(root, "methods/repeat.md", m, METHOD_BODY)
        r = load()
        assert r.nodes["method:repeat"].effective_status == "draft"  # whole-file reference includes the draft
        m["decisions"][0]["references"] = ["entities/customers.yaml#missing"]
        write(root, "methods/repeat.md", m, METHOD_BODY)
        assert any(d.code == "reference.anchor" for d in load().errors)
        (root / "evals/seeds/repeat.seed.yaml").unlink()  # dependency cases above; authoring cases below
        def check(data=None, body=METHOD_BODY):
            write(root, "methods/repeat.md", data or method(), body)
            return load()
        # A syntactically valid canonical ID cannot redirect a metric declaration
        # to a method of the wrong kind.
        bad = method(); bad["metrics"] = ["method:repeat"]
        assert "reference.missing" in {d.code for d in check(bad).errors}
        for code in ("```sql\nselect 1\n```", "```sql title=example\nselect 1\n```", "~~~python\nresult = 1\n~~~",
                     "```\nselect * from orders\n```", "```\nresult = run_query()\n```",
                     "SELECT COUNT(*) FROM orders"):
            assert "method.code" in {d.code for d in check(body=METHOD_BODY + "\n" + code).errors}
        procedural = METHOD_BODY.replace("Count canonical identities", "Keep identities with count >= 3")
        assert "constant.undeclared" in {d.code for d in check(body=procedural).errors}
        for expression in ("cohort_size - 5", "cohort_size * 1e3"):
            body = METHOD_BODY.replace("Count canonical identities", "Compute " + expression)
            assert "constant.undeclared" in {d.code for d in check(body=body).errors}
        declared = method(); declared["constants"] = [{"name": "repeat_limit", "value": 3,
                                                       "note": "Fictional fixed business limit."}]
        assert "constant.undeclared" not in {d.code for d in check(declared, procedural).errors}
        dated = METHOD_BODY.replace("Count canonical identities", "Count identities since 2026-01-01")
        assert "parameter.literal_date" in {d.code for d in check(body=dated).errors}
        illustrative = METHOD_BODY + "\n## Worked parameterization\n\nExample: count >= 3 on 2026-01-01.\n"
        assert not check(body=illustrative).errors
        citation = METHOD_BODY.replace("(`identity`)", "(`identity`; [policy](https://example.invalid/2026-01-01))")
        assert not check(body=citation).errors
        unused = method(); unused["parameters"].append({"name": "unused", "note": "Not referenced."})
        assert "parameter.unused" in {d.code for d in check(unused).errors}
        hyphenated = method(); hyphenated["parameters"][0]["name"] = "report-window"
        hyphenated["decisions"][0]["rule"] = "Use canonical identity in <report-window>."
        body = METHOD_BODY.replace("<window>", "<report-window>")
        assert not check(hyphenated, body).errors
        assert "parameter.undeclared" in {d.code for d in check(hyphenated, body + "\n<undeclared-window>\n").errors}
        optional = method(); optional["output"]["optional_columns"] = ["channel"]
        assert "output.optional_decision" in {d.code for d in check(optional).errors}
        optional["decisions"][0]["rule"] += " Include channel only for a sliced result."
        assert not check(optional).errors
        incomplete = method(); incomplete["status"] = "draft"
        r = check(incomplete, procedural)
        assert not r.errors and "constant.undeclared" in {d.code for d in r.diagnostics}
        missing_note = method(); missing_note["parameters"][0].pop("note")
        assert "schema.invalid" in {d.code for d in check(missing_note).errors}
        write(root, "domains/sales/metrics/other.yaml", metric("other"))
        undeclared = method(); undeclared["decisions"][0]["references"] = ["domains/sales/metrics/other.yaml"]
        assert "method.metric_reference" in {d.code for d in check(undeclared).errors}
        undeclared["metrics"].append("other")
        assert not check(undeclared).errors

        # A method cannot bypass a base metric's mandatory filters by composing
        # an arithmetic metric whose own filter list is empty.
        derived = metric("orders_twice", lineage="inherit", expression={
            "measure": "metric(orders) + metric(orders)", "allowed_dimensions": ["channel", "date"]})
        write(root, "domains/sales/metrics/orders_twice.yaml", derived)
        composed = method(); composed["metrics"] = ["orders_twice"]
        composed["decisions"][0]["constraints"] = [{"metric": "orders_twice",
            "filter": {"field": "test", "op": "=", "value": True}}]
        result = check(composed)
        assert "constraint.override_required" in {d.code for d in result.errors}
        assert any(d.target == "metric:sales.orders" for d in result.errors if d.code == "constraint.override_required")
        composed["decisions"][0]["overrides"] = {"metric": "orders_twice", "filter_field": "test",
                                                  "reason": "Explicit fictional sensitivity comparison."}
        assert not check(composed).errors
        # Matching one component does not prove agreement with every branch.
        opposite = metric("test_orders")
        opposite["expression"]["mandatory_filters"][0]["value"] = True
        write(root, "domains/sales/metrics/test_orders.yaml", opposite)
        derived["expression"]["measure"] = "metric(orders) + metric(test_orders)"
        write(root, "domains/sales/metrics/orders_twice.yaml", derived)
        composed["decisions"][0].pop("overrides")
        composed["decisions"][0]["constraints"][0]["filter"]["value"] = False
        result = check(composed)
        assert any(d.target == "metric:sales.test_orders" and d.code == "constraint.override_required" for d in result.errors)
    print("test_methods: OK")


if __name__ == "__main__":
    run()
