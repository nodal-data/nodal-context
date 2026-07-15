"""Golden behavior test for scripts/query_history_extract.py — stdlib only, no pytest.

Two fixtures cover both canonicalizer paths: the per-identity ACCOUNT_USAGE shape
(uppercase keys, {"rows": ...} wrapper, one row per fingerprint x identity) and
the raw INFORMATION_SCHEMA shape (bare array, per-query rows the client
canonicalizer must collapse). Assertions cover per-identity classification and
mixed traffic, evidence, both admission branches, ETL/dbt exclusion, the lexer,
table/agg extraction, conflict grouping, effective-window reporting, ranking,
degradation, determinism, argument validation, and the loud stubs.

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

NO_OVERRIDES = {"bi_users": [], "bi_roles": [], "bi_warehouses": [],
                "exclude_users": []}


def _findings(rows_path, *extra_args):
    out = Path(tempfile.mkdtemp()) / "findings.json"
    rc = qhe.main(["--rows", str(rows_path), "--platform", "snowflake",
                   "-o", str(out), *extra_args])
    assert rc == 0
    return json.loads(out.read_text())


def _findings_from_rows(rows, *extra_args):
    d = Path(tempfile.mkdtemp())
    (d / "rows.json").write_text(json.dumps(rows))
    return _findings(d / "rows.json", *extra_args)


def _cluster(f, fingerprint):
    return next(c for c in f["clusters"] if c["fingerprint"] == fingerprint)


def _identity(user="U", role="", warehouse="", query_tag="", sample=""):
    return {"user": user, "role": role, "warehouse": warehouse,
            "query_tag": query_tag, "sample_text": sample}


def run():
    # ---- aggregated (account_usage / warehouse canonicalizer) path ----
    f = _findings(AGG_FIXTURE)
    assert f["source"] == "query_history"
    assert f["platform"] == "snowflake" and f["scope"] == "account_usage"
    assert f["thresholds"] == {"min_count": 5, "min_users": 2}
    assert f["window_days"] == 90 and "window_days_requested" not in f

    # all-ETL / all-dbt clusters excluded: counted, absent from clusters[]
    assert f["pools"] == {"bi_service": 4, "ad_hoc": 3, "excluded": 2}
    dropped = {"fp_etl_fivetran", "fp_dbt_test"}
    assert not dropped & {c["fingerprint"] for c in f["clusters"]}
    assert len(f["clusters"]) == 7

    # pooling with evidence
    tab = _cluster(f, "fp_tableau_net")
    assert tab["pool"] == "bi_service"
    assert any("tableau" in e for e in tab["pool_evidence"])

    # mixed traffic: the dbt identity's executions are subtracted and disclosed,
    # NOT allowed to suppress the dashboard shape
    mixed = _cluster(f, "fp_mixed_daily")
    assert mixed["pool"] == "bi_service" and mixed["admitted"]
    assert mixed["n_executions"] == 30 and mixed["n_executions_excluded"] == 10
    assert mixed["users"] == ["TABLEAU_SVC"]  # DBT_CLOUD dropped from identity sets
    assert any("excluded 10 execution(s)" in e and "dbt marker" in e
               for e in mixed["pool_evidence"])

    # QUERY_TAG is a classification dim (Sigma sets it; stronger than usernames)
    sigma = _cluster(f, "fp_sigma_tag")
    assert sigma["pool"] == "bi_service"
    assert any("query_tag" in e and "sigma" in e for e in sigma["pool_evidence"])
    assert sigma["query_tags"] == ["sigma-computed workbook=Revenue"]

    # admission: bi_service needs only min_count; ad_hoc needs min_users too;
    # identity rows merge into cluster totals (5+3 executions, 2 users)
    adhoc = _cluster(f, "fp_adhoc_netref")
    assert adhoc["pool"] == "ad_hoc" and adhoc["admitted"]
    assert adhoc["n_executions"] == 8 and adhoc["n_users"] == 2
    below = _cluster(f, "fp_below_threshold")
    assert not below["admitted"]  # n=3 < 5, still listed

    # table extraction: dotted names uppercased, CTE name not a table
    human = _cluster(f, "fp_human_sessions")
    assert human["tables"] == ["ANALYTICS.MART.DIM_CLIENTS",
                               "ANALYTICS.MART.FCT_SESSIONS"]
    assert human["admitted"] and human["n_users"] == 3

    # conflict grouping: 3 admitted clusters on FCT_ORDERS with DISTINCT
    # aggregate signatures -> one group
    assert len(f["conflict_groups"]) == 1
    g = f["conflict_groups"][0]
    assert g["tables"] == ["ANALYTICS.MART.FCT_ORDERS"]
    assert g["members"] == ["fp_tableau_net", "fp_looker_gross", "fp_adhoc_netref"]
    assert g["agg_signatures"]["fp_tableau_net"] == ["sum(net_revenue)"]
    assert tab["conflict_group"] == g["id"]
    assert human["conflict_group"] is None

    # emitted order: admitted first, then by executions
    assert [c["fingerprint"] for c in f["clusters"][:2]] == ["fp_tableau_net",
                                                             "fp_looker_gross"]
    assert f["clusters"][-1]["fingerprint"] == "fp_below_threshold"

    # degradation + coverage (counts only)
    assert f["unavailable"] == ["viewer_counts"]
    assert f["coverage"] == {"rows_in": 13, "clusters_total": 9,
                             "clusters_admitted": 6, "conflict_groups": 1}

    # determinism: identical output on a second run
    assert json.dumps(f, sort_keys=True) == json.dumps(_findings(AGG_FIXTURE),
                                                       sort_keys=True)

    # ---- classification unit checks ----
    # token boundaries: no substring false positives
    assert qhe._token_match("MODE_SVC", "mode")
    assert not qhe._token_match("MODELING_ANALYST", "mode")
    assert qhe._token_match("DBT_CLOUD", "dbt")
    assert not qhe._token_match("PRODBT", "dbt")
    # explicit override beats heuristic; exclusion beats BI; content beats identity
    klass, why = qhe.classify_identity(_identity(user="JANE"),
                                       dict(NO_OVERRIDES, bi_users=["jane"]))
    assert klass == "bi" and "listed in --bi-users" in why
    klass, _ = qhe.classify_identity(_identity(user="TABLEAU_SVC"),
                                     dict(NO_OVERRIDES, exclude_users=["tableau_svc"]))
    assert klass == "etl"
    klass, _ = qhe.classify_identity(
        _identity(user="TABLEAU_SVC", sample='SELECT 1 /* {"app": "dbt"} */'),
        NO_OVERRIDES)
    assert klass == "dbt"
    # dbt content markers individually
    assert qhe.dbt_markers("... ) dbt_internal_test")
    assert qhe.dbt_markers("select * from __dbt__cte__stg_orders")
    assert qhe.dbt_markers("SELECT 1 -- plain query, app not dbt") == []

    # ---- lexer: comment markers inside literals are NOT comments ----
    a = qhe.canonicalize("SELECT '-- not a comment', x FROM t WHERE d > '2026-01-01'")
    assert a == "select ?, x from t where d > ?"
    b = qhe.canonicalize("SELECT x FROM t WHERE n IN (1, 2, 3) -- real comment")
    c = qhe.canonicalize("select x  from t where n IN (5,6)")
    assert b == c and "in (?)" in b
    assert qhe.canonicalize("SELECT 'it''s' FROM t") == "select ? from t"
    # literals can't fake tables or aggregates
    assert qhe.extract_tables("SELECT 'FROM fake_table' FROM real_t") == ["REAL_T"]
    assert qhe.agg_signatures("SELECT 'sum(nope)', COUNT(*) FROM t") == ["count(*)"]

    # ---- conflict rule: identical signatures are NOT a conflict ----
    same = [{"fingerprint": f"fp{i}", "n_executions": 10, "admitted": True,
             "tables": ["T"], "agg_signatures": ["sum(revenue)"],
             "conflict_group": None} for i in range(2)]
    assert qhe.find_conflict_groups(same) == []
    many = [{"fingerprint": f"fp{i}", "n_executions": 10, "admitted": True,
             "tables": ["T"], "agg_signatures": [f"sum(col_{i})"],
             "conflict_group": None} for i in range(9)]
    assert qhe.find_conflict_groups(many) == []  # >8 members = hot table

    # ---- classification sees FULL identity sets; truncation only on output ----
    rows = [{"FINGERPRINT": "fp_wide", "USER_NAME": f"USER_{i:02d}",
             "ROLE_NAME": "ANALYST", "WAREHOUSE_NAME": "WH", "QUERY_TAG": "",
             "N_EXECUTIONS": 1, "SAMPLE_TEXT": "SELECT COUNT(*) FROM T",
             "FIRST_SEEN": "2026-07-01T00:00:00Z", "LAST_SEEN": "2026-07-01T00:00:00Z"}
            for i in range(24)]
    rows.append(dict(rows[0], USER_NAME="ZZ_TABLEAU_SVC"))  # alphabetically last
    fw = _findings_from_rows(rows)
    wide = _cluster(fw, "fp_wide")
    assert wide["pool"] == "bi_service"       # classified before truncation
    assert len(wide["users"]) == 20            # truncated only in the output

    # ---- --top ranks admitted first, never crowded out by loud noise ----
    top_rows = [
        {"FINGERPRINT": "fp_noise", "USER_NAME": "JANE", "ROLE_NAME": "",
         "WAREHOUSE_NAME": "", "QUERY_TAG": "", "N_EXECUTIONS": 100,
         "SAMPLE_TEXT": "SELECT * FROM T1", "FIRST_SEEN": "", "LAST_SEEN": ""},
        {"FINGERPRINT": "fp_bi", "USER_NAME": "TABLEAU_SVC", "ROLE_NAME": "",
         "WAREHOUSE_NAME": "", "QUERY_TAG": "", "N_EXECUTIONS": 10,
         "SAMPLE_TEXT": "SELECT COUNT(*) FROM T2", "FIRST_SEEN": "", "LAST_SEEN": ""},
    ]
    ft = _findings_from_rows(top_rows, "--top", "1")
    assert [c["fingerprint"] for c in ft["clusters"]] == ["fp_bi"]  # admitted wins
    assert ft["coverage"]["clusters_total"] == 2  # coverage still sees everything

    # ---- raw (information_schema / client canonicalizer) path ----
    fr = _findings(RAW_FIXTURE, "--scope", "information_schema", "--min-count", "2")
    assert fr["scope"] == "information_schema"
    # effective window reported honestly (7-day cap), request preserved
    assert fr["window_days"] == 7 and fr["window_days_requested"] == 90
    assert set(fr["unavailable"]) == {"viewer_counts", "query_parameterized_hash",
                                      "result_limit_pre_filter",
                                      "window_beyond_7_days"}
    # two literal-differing queries collapse to ONE client fingerprint
    assert fr["coverage"]["rows_in"] == 3 and fr["coverage"]["clusters_total"] == 2
    merged = next(c for c in fr["clusters"] if c["n_executions"] == 2)
    assert merged["fingerprint_source"] == "client"
    assert merged["users"] == ["BOB", "JANE"] and merged["n_users"] == 2
    assert merged["admitted"]
    assert merged["tables"] == ["ANALYTICS.MART.FCT_ORDERS"]
    assert merged["first_seen"] == "2026-07-10T09:00:00Z"
    assert merged["last_seen"] == "2026-07-12T10:30:00Z"

    # ---- emit-sql + stubs + argument validation ----
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert qhe.main(["--emit-sql", "--platform", "snowflake"]) == 0
    sql = buf.getvalue()
    assert "query_parameterized_hash" in sql and "LIMIT 5000" in sql
    assert "GROUP BY 1, 2, 3, 4, 5" in sql and "QUALIFY" in sql
    assert "query_tag" in sql and "DATEADD(day, -90," in sql

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        assert qhe.main(["--emit-sql", "--platform", "snowflake",
                         "--scope", "information_schema"]) == 0
    isql = buf.getvalue()
    assert "INFORMATION_SCHEMA.QUERY_HISTORY" in isql
    assert "DATEADD(day, -7," in isql          # effective (capped) window in SQL
    assert "BEFORE the outer" in isql          # RESULT_LIMIT pre-filter disclosed
    assert "query_tag" in isql

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

    for bad in (["--top", "0"], ["--days", "-3"], ["--min-count", "0"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                qhe.main(["--emit-sql", "--platform", "snowflake", *bad])
        except SystemExit as e:
            assert e.code == 2  # argparse rejects non-positive integers
        else:
            raise AssertionError(f"{bad} was not rejected")

    print("test_query_history_extract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
