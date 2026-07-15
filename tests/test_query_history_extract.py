"""Golden behavior test for scripts/query_history_extract.py — stdlib only, no pytest.

Two fixtures cover both canonicalizer paths: the aggregated ACCOUNT_USAGE shape
(uppercase keys, {"rows": ...} wrapper, one row per warehouse fingerprint) and the
raw INFORMATION_SCHEMA shape (bare array, per-query rows the client canonicalizer
must collapse). Assertions cover pooling + evidence, both admission branches, ETL
exclusion, table/agg extraction, conflict grouping, degradation, determinism, and
the loud not-implemented stubs.

Run: python3 tests/test_query_history_extract.py   (exit 0 = pass)
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import query_history_extract as qhe  # noqa: E402

AGG_FIXTURE = ROOT / "tests" / "fixtures" / "query_history_rows_snowflake.json"
RAW_FIXTURE = ROOT / "tests" / "fixtures" / "query_history_rows_snowflake_raw.json"


def _findings(rows_path, *extra_args):
    out = Path(tempfile.mkdtemp()) / "findings.json"
    rc = qhe.main(["--rows", str(rows_path), "--platform", "snowflake",
                   "-o", str(out), *extra_args])
    assert rc == 0
    return json.loads(out.read_text())


def _cluster(f, fingerprint):
    return next(c for c in f["clusters"] if c["fingerprint"] == fingerprint)


def run():
    # ---- aggregated (account_usage / warehouse canonicalizer) path ----
    f = _findings(AGG_FIXTURE)
    assert f["source"] == "query_history"
    assert f["platform"] == "snowflake" and f["scope"] == "account_usage"
    assert f["thresholds"] == {"min_count": 5, "min_users": 2}

    # ETL cluster and dbt-stamped cluster excluded: counted, absent from clusters[]
    assert f["pools"] == {"bi_service": 2, "ad_hoc": 3, "excluded": 2}
    dropped = {"fp_etl_fivetran", "fp_dbt_test"}
    assert not dropped & {c["fingerprint"] for c in f["clusters"]}
    assert len(f["clusters"]) == 5

    # pooling with evidence; JSON-string ARRAY_AGG tolerated (_as_list)
    tab = _cluster(f, "fp_tableau_net")
    assert tab["pool"] == "bi_service"
    assert any("tableau" in e for e in tab["pool_evidence"])
    look = _cluster(f, "fp_looker_gross")
    assert look["users"] == ["LOOKER_SVC"] and look["pool"] == "bi_service"

    # admission: bi_service needs only min_count; ad_hoc needs min_users too
    assert tab["admitted"] and look["admitted"]
    adhoc = _cluster(f, "fp_adhoc_netref")
    assert adhoc["pool"] == "ad_hoc" and adhoc["admitted"]  # n=8>=5, users=2>=2
    below = _cluster(f, "fp_below_threshold")
    assert not below["admitted"]  # n=3 < 5, still listed

    # table extraction: dotted names uppercased, CTE name not a table
    human = _cluster(f, "fp_human_sessions")
    assert human["tables"] == ["ANALYTICS.MART.DIM_CLIENTS",
                               "ANALYTICS.MART.FCT_SESSIONS"]
    assert "RECENT" not in human["tables"]
    assert human["admitted"]  # n=12, users=3

    # conflict grouping: 3 admitted aggregate clusters on FCT_ORDERS -> one group
    assert len(f["conflict_groups"]) == 1
    g = f["conflict_groups"][0]
    assert g["tables"] == ["ANALYTICS.MART.FCT_ORDERS"]
    assert g["members"] == ["fp_tableau_net", "fp_looker_gross", "fp_adhoc_netref"]
    assert g["agg_signatures"]["fp_tableau_net"] == ["sum(net_revenue)"]
    assert g["agg_signatures"]["fp_looker_gross"] == ["sum(gross_revenue)"]
    assert tab["conflict_group"] == g["id"]
    assert human["conflict_group"] is None  # unique table set, no conflict

    # degradation + coverage (counts only)
    assert f["unavailable"] == ["viewer_counts"]
    assert f["coverage"] == {"rows_in": 7, "clusters_total": 7,
                             "clusters_admitted": 4, "conflict_groups": 1}

    # dbt content markers: query comment, test scaffolding, ephemeral CTEs —
    # content beats identity (the marker excludes even a declared BI user's query)
    assert qhe.dbt_markers('SELECT 1 /* {"app": "dbt", "node_id": "m.x"} */')
    assert qhe.dbt_markers("... ) dbt_internal_test")
    assert qhe.dbt_markers("select * from __dbt__cte__stg_orders")
    assert qhe.dbt_markers("SELECT 1 -- plain query, app not dbt") == []

    # thresholds are CLI-tunable: min-count 50 demotes everything but tableau
    f50 = _findings(AGG_FIXTURE, "--min-count", "50")
    assert sum(1 for c in f50["clusters"] if c["admitted"]) == 1

    # explicit override beats heuristic: JANE declared a BI user
    pool, ev = qhe.classify_pool(["JANE"], [], [], {
        "bi_users": ["jane"], "bi_roles": [], "bi_warehouses": [],
        "exclude_users": []})
    assert pool == "bi_service" and "listed in --bi-users" in ev[0]
    # exclusion beats BI: an explicitly excluded user never becomes a candidate
    pool, _ = qhe.classify_pool(["TABLEAU_SVC"], [], [], {
        "bi_users": [], "bi_roles": [], "bi_warehouses": [],
        "exclude_users": ["tableau_svc"]})
    assert pool == "excluded"

    # hot table: >8 members is not a conflict group
    many = [{"fingerprint": f"fp{i}", "n_executions": 10, "admitted": True,
             "tables": ["T"], "agg_signatures": ["count(*)"],
             "conflict_group": None} for i in range(9)]
    assert qhe.find_conflict_groups(many) == []

    # determinism: identical output on a second run
    assert json.dumps(f, sort_keys=True) == json.dumps(_findings(AGG_FIXTURE),
                                                       sort_keys=True)

    # ---- raw (information_schema / client canonicalizer) path ----
    fr = _findings(RAW_FIXTURE, "--scope", "information_schema", "--min-count", "2")
    assert fr["scope"] == "information_schema"
    assert set(fr["unavailable"]) == {"viewer_counts", "query_parameterized_hash",
                                      "window_beyond_7_days"}
    # two literal-differing queries collapse to ONE client fingerprint
    assert fr["coverage"]["rows_in"] == 3 and fr["coverage"]["clusters_total"] == 2
    merged = next(c for c in fr["clusters"] if c["n_executions"] == 2)
    assert merged["fingerprint_source"] == "client"
    assert merged["users"] == ["BOB", "JANE"] and merged["n_users"] == 2
    assert merged["admitted"]  # n=2>=2, users=2>=2
    assert merged["tables"] == ["ANALYTICS.MART.FCT_ORDERS"]
    assert merged["first_seen"] == "2026-07-10T09:00:00Z"
    assert merged["last_seen"] == "2026-07-12T10:30:00Z"

    # canonicalizer itself: literals, case, whitespace, IN-lists
    a = qhe.canonicalize("SELECT x FROM t WHERE d > '2026-01-01' AND n IN (1, 2, 3)")
    b = qhe.canonicalize("select x  from t where d > '2026-06-01' and n IN (5,6)")
    assert a == b and "in (?)" in a

    # ---- emit-sql + stubs ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert qhe.main(["--emit-sql", "--platform", "snowflake"]) == 0
    sql = buf.getvalue()
    assert "query_parameterized_hash" in sql and "LIMIT 5000" in sql
    assert "DATEADD(day, -90," in sql

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert qhe.main(["--emit-sql", "--platform", "snowflake",
                         "--scope", "information_schema", "--days", "30"]) == 0
    assert "INFORMATION_SCHEMA.QUERY_HISTORY" in buf.getvalue()
    assert "DATEADD(day, -7," in buf.getvalue()  # fallback window capped at 7

    for platform in ("bigquery", "databricks", "redshift", "fabric"):
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                qhe.main(["--emit-sql", "--platform", platform])
        except SystemExit as e:
            assert e.code == 2
            assert "not implemented" in err.getvalue()
            assert "Implemented: snowflake" in err.getvalue()
        else:
            raise AssertionError(f"stub platform {platform} did not exit loudly")

    print("test_query_history_extract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
