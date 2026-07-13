"""Offline tests for the eval_harness runner — the LLM client is mocked, no key/network.

Needs PyYAML (the acf adapter parses seeds); self-skips with exit 0 if it's absent.

Run: python3 tests/test_eval_harness.py   (exit 0 = pass/skip)
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval_harness import adapters, client, grader, report, run  # noqa: E402
from eval_harness.grader import PASS, FAIL, SKIPPED  # noqa: E402

HEALTHCARE = ROOT / "examples" / "example-healthcare-company"


def run_tests():
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("test_eval_harness: PyYAML missing; skipped")
        return

    # --- adapter: ACF -> NCR ----------------------------------------------------
    ncr = adapters.get_builder("acf")(HEALTHCARE, ["session-financials"])
    assert ncr.domains() == ["session-financials"], ncr.domains()
    confirmed = ncr.seeds_for("session-financials", "confirmed")
    assert len(confirmed) == 2, [s.question for s in confirmed]   # both example seeds confirmed
    kinds = sorted(s.kind for s in confirmed)
    assert kinds == ["sql_shape", "value_at_snapshot"], kinds
    ctx = ncr.context_for("session-financials")
    # context-on payload carries the routing triggers the seeds test
    assert "Payer X" in ctx and "45-day" in ctx, "context blob missing routing triggers"

    # unknown adapter errors
    try:
        adapters.get_builder("nope"); assert False
    except ValueError:
        pass

    # --- adapters: raw / ktx / dbt -> context-only NCRs --------------------------
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # raw: subdirs are domains, root-level md is shared
        (td / "raw" / "finance").mkdir(parents=True)
        (td / "raw" / "glossary.md").write_text("# Glossary\nGMV means gross booked value.")
        (td / "raw" / "finance" / "notes.md").write_text("Exclude test payers.")
        ncr = adapters.get_builder("raw")(td / "raw")
        assert ncr.domains() == ["finance"] and not ncr.seeds
        assert "GMV" in ncr.context_for("finance") and "test payers" in ncr.context_for("finance")
        # flat layout -> one domain named after the dir
        (td / "flat").mkdir()
        (td / "flat" / "only.md").write_text("just this")
        assert adapters.get_builder("raw")(td / "flat").domains() == ["flat"]

        # ktx: semantic-layer/<connection>/*.yaml + wiki, keyed descriptions
        conn = td / "ktx" / "semantic-layer" / "warehouse-1"
        conn.mkdir(parents=True)
        (conn / "orders.yaml").write_text(
            "name: orders\ntable: analytics.orders\ngrain: [order_id]\n"
            "columns:\n  - name: order_id\n    type: string\n"
            "    descriptions: {ai: robo, user: Unique order id.}\n"
            "measures:\n  - name: total_revenue\n    expr: SUM(total_amount)\n"
            "    filter: status = 'completed'\n"
            "segments:\n  - name: completed\n    expr: status = 'completed'\n"
            "joins:\n  - to: customers\n    on: orders.customer_id = customers.customer_id\n"
            "    relationship: many_to_one\n")
        wiki = td / "ktx" / "wiki" / "global"
        wiki.mkdir(parents=True)
        (wiki / "revenue-policy.md").write_text(
            "---\nsummary: Revenue counting policy.\ntags: [revenue]\n---\nNever count refunds.")
        ncr = adapters.get_builder("ktx")(td / "ktx")
        assert ncr.domains() == ["warehouse-1"] and not ncr.seeds
        ctx = ncr.context_for("warehouse-1")
        assert "Unique order id." in ctx and "robo" not in ctx   # user desc outranks ai
        assert "SUM(total_amount)" in ctx and "many_to_one" in ctx
        assert "Never count refunds." in ctx and "Revenue counting policy." in ctx

        # dbt: manifest branch — fqn folder = domain, grain from unique test, metrics shared
        manifest = {
            "metadata": {"project_name": "shop", "dbt_schema_version": "…/v12.json"},
            "nodes": {
                "model.shop.fct_orders": {
                    "resource_type": "model", "name": "fct_orders",
                    "relation_name": "analytics.fct_orders",
                    "description": "One row per order.",
                    "fqn": ["shop", "marts", "fct_orders"],
                    "columns": {"order_id": {"name": "order_id", "description": "PK."}},
                },
                "test.shop.unique_fct_orders_order_id": {
                    "resource_type": "test", "column_name": "order_id",
                    "attached_node": "model.shop.fct_orders",
                    "test_metadata": {"name": "unique", "kwargs": {}},
                },
            },
            "metrics": {"metric.shop.revenue": {
                "name": "revenue", "type": "simple", "description": "Booked revenue."}},
            "semantic_models": {"semantic_model.shop.orders": {
                "name": "orders", "measures": [{"name": "total_amount"}]}},
        }
        (td / "dbt_proj" / "target").mkdir(parents=True)
        (td / "dbt_proj" / "target" / "manifest.json").write_text(json.dumps(manifest))
        ncr = adapters.get_builder("dbt")(td / "dbt_proj")
        assert ncr.domains() == ["marts"] and not ncr.seeds
        ctx = ncr.context_for("marts")
        assert "One row per order." in ctx and "order_id" in ctx
        assert "Grain (from unique tests): order_id" in ctx
        assert "revenue" in ctx and "Booked revenue." in ctx     # metrics shared block
        # dbt: bare schema.yml fallback (no manifest)
        (td / "dbt_src" / "models" / "marts").mkdir(parents=True)
        (td / "dbt_src" / "models" / "marts" / "schema.yml").write_text(
            "models:\n  - name: dim_customers\n    description: One row per customer.\n")
        ncr = adapters.get_builder("dbt")(td / "dbt_src")
        assert ncr.domains() == ["marts"]
        assert "One row per customer." in ncr.context_for("marts")

        # skill: a Claude data-analysis skill — SKILL.md shared, one domain per
        # references file, entities/metrics references cross-domain
        sk = td / "acme-data-analyst"
        (sk / "references" / "tables").mkdir(parents=True)
        (sk / "SKILL.md").write_text(
            "---\nname: acme-data-analyst\ndescription: Acme data skill.\n---\n"
            "# Acme Data Analysis\nDialect: Snowflake. Always exclude test orders.")
        (sk / "references" / "entities.md").write_text(
            "Customer means a user with >=1 purchase.")
        (sk / "references" / "metrics.md").write_text("GMV = SUM(order_total_gross).")
        (sk / "references" / "orders.md").write_text("FCT_ORDERS: one row per order.")
        (sk / "references" / "tables" / "customers.md").write_text(
            "DIM_CUSTOMERS joins on customer_id.")
        (sk / "references" / "dashboards.json").write_text("{}")   # non-md: ignored
        ncr = adapters.get_builder("skill")(sk)
        assert ncr.domains() == ["customers", "orders"] and not ncr.seeds
        ctx = ncr.context_for("orders")
        assert "one row per order" in ctx
        assert "exclude test orders" in ctx                    # SKILL.md body shared
        assert ">=1 purchase" in ctx and "SUM(order_total_gross)" in ctx  # shared refs
        assert "name: acme-data-analyst" not in ctx            # frontmatter stripped
        assert "one row per order" not in ncr.context_for("customers")   # per-domain
        # packaged zip (the package_data_skill.py deliverable) reads the same
        import zipfile as zf_mod
        zpath = td / "acme-data-analyst.zip"
        with zf_mod.ZipFile(zpath, "w") as zf:
            for f in sk.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(sk.parent))
        ncr = adapters.get_builder("skill")(zpath)
        assert ncr.domains() == ["customers", "orders"]
        assert "exclude test orders" in ncr.context_for("orders")
        # no per-domain references -> one domain named from frontmatter
        solo = td / "solo-skill"
        solo.mkdir()
        (solo / "SKILL.md").write_text("---\nname: shop-data\n---\nAll context here.")
        ncr = adapters.get_builder("skill")(solo)
        assert ncr.domains() == ["shop-data"]
        assert "All context here." in ncr.context_for("shop-data")

        # --seeds attaches external ground truth to a context-only adapter
        (td / "seeds").mkdir()
        (td / "seeds" / "q1.seed.yaml").write_text(
            "question: Total revenue last month?\ndomain: finance\nintent: t\n"
            "expected:\n  kind: sql_shape\n  must_include: [excludes test payers]\n"
            "provenance: interview\nstatus: confirmed\n")

        def fake_gen(question, context_text=None, model=None):
            return {"sql": "SELECT 1 -- ctx" if context_text else "SELECT 1", "assumptions": []}

        orig = (client.available, client.generate, client.judge, client.MAX_CONTEXT_CHARS)
        client.available = lambda: True
        client.generate = fake_gen
        client.judge = lambda sql, expected, model=None: {"passed": "ctx" in sql, "reason": ""}
        try:
            rc = run.main(["--adapter", "raw", "--root", str(td / "raw"),
                           "--seeds", str(td / "seeds"), "--mode", "inject",
                           "--out", str(td / "report.md")])
            assert rc == 0
            assert "truncated" not in (td / "report.md").read_text()
            # oversized context -> truncation warning lands in the report
            client.MAX_CONTEXT_CHARS = 10
            run.main(["--adapter", "raw", "--root", str(td / "raw"),
                      "--seeds", str(td / "seeds"), "--out", str(td / "report.md")])
            assert "truncated" in (td / "report.md").read_text()
            client.MAX_CONTEXT_CHARS = orig[3]
            # no seeds anywhere -> helpful message, exit 0, no LLM calls needed
            assert run.main(["--adapter", "raw", "--root", str(td / "raw")]) == 0
        finally:
            client.available, client.generate, client.judge, client.MAX_CONTEXT_CHARS = orig

    # --- client: prompt-cache content shape (no network — _structured_call mocked)
    calls = []
    orig_call = client._structured_call
    client._structured_call = lambda system, content, schema, model: calls.append(content) or {}
    try:
        client.generate("What is GMV?", "governed context here")
        client.generate("What is GMV?", None)
    finally:
        client._structured_call = orig_call
    with_ctx, without_ctx = calls
    # context block first (stable cached prefix), question after, cache_control set
    assert isinstance(with_ctx, list) and len(with_ctx) == 2
    assert with_ctx[0]["cache_control"] == {"type": "ephemeral"}
    assert "governed context here" in with_ctx[0]["text"]
    assert "What is GMV?" in with_ctx[1]["text"] and "cache_control" not in with_ctx[1]
    assert isinstance(without_ctx, str) and "What is GMV?" in without_ctx

    # --- grader ----------------------------------------------------------------
    sql_shape = {"kind": "sql_shape", "must_include": ["x"], "must_exclude": ["y"]}
    assert grader.grade(sql_shape, "SELECT 1", lambda s, e: {"passed": True, "reason": "ok"}).status == PASS
    bad = grader.grade(sql_shape, "SELECT 1", lambda s, e: {"passed": False, "reason": "missing x"})
    assert bad.status == FAIL and bad.reason == "missing x"
    # value_at_snapshot is skipped without calling the judge
    called = []
    skip = grader.grade({"kind": "value_at_snapshot", "value": 0.9}, "SELECT 1",
                        lambda s, e: called.append(1) or {"passed": True})
    assert skip.status == SKIPPED and not called

    # --- report rendering ------------------------------------------------------
    dr = [{
        "domain": "session-financials", "drafts": 1,
        "seeds": [
            {"question": "Qa", "kind": "sql_shape", "off": FAIL, "on": PASS, "on_reason": ""},
            {"question": "Qb", "kind": "sql_shape", "off": FAIL, "on": FAIL,
             "on_reason": "forgot the 45-day cutoff"},
            {"question": "Qc", "kind": "value_at_snapshot", "off": SKIPPED,
             "on": SKIPPED, "on_reason": ""},
        ],
    }]
    text = report.render(dr)
    assert "context-off → 0%" in text          # 0 of 2 gradable
    assert "context-on  → 50%" in text          # 1 of 2 gradable
    assert "(+50 pts)" in text
    assert "1 value_at_snapshot skipped" in text
    assert 'forgot the 45-day cutoff  [sql_shape]' in text   # punch-list only the on-fail
    assert "Qa" not in text                      # passing seed not in punch-list
    assert "truncated" not in text               # no warning when context fits
    dr[0]["context_truncated"] = True
    assert "truncated" in report.render(dr)      # warning surfaces in the report

    # --- run.main with a fully mocked client -----------------------------------
    # context-off always "misses" the exclusion; context-on always passes.
    def fake_generate(question, context_text=None, model=None):
        return {"sql": "SELECT 1 -- with-context" if context_text else "SELECT 1", "assumptions": []}

    def fake_judge(sql, expected, model=None):
        return {"passed": "with-context" in sql, "reason": "" if "with-context" in sql else "missed caveat"}

    orig = (client.available, client.generate, client.judge)
    client.available = lambda: True
    client.generate = fake_generate
    client.judge = fake_judge
    try:
        rc = run.main(["--adapter", "acf", "--root", str(HEALTHCARE),
                       "--domains", "session-financials", "--report", "pr-comment"])
        assert rc == 0
        # no-key path: graceful skip, exit 0
        client.available = lambda: False
        assert run.main(["--root", str(HEALTHCARE), "--domains", "session-financials"]) == 0
    finally:
        client.available, client.generate, client.judge = orig

    print("test_eval_harness: OK")


if __name__ == "__main__":
    run_tests()
