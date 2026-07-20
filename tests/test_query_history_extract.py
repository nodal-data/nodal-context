"""Golden behavior test for scripts/query_history_extract.py — stdlib only, no pytest.

Two fixtures cover both normalization paths: the per-(identity x dbt-flag)
ACCOUNT_USAGE/INFORMATION_SCHEMA shape (uppercase keys, {"rows": ...} wrapper,
warehouse-native fingerprints) and the raw shape for platforms without a native
hash (bare array, per-query rows the client canonicalizer must collapse).
Assertions cover per-class execution counting, mixed traffic, evidence, admission
per traffic class, ETL/dbt exclusion (including the deterministic is_dbt flag),
content-level demotion (system chrome / catalog polling / BI UI chrome) with
admitted-only emission and --emit-rejected, the identity census and
service-account flagging, the lexer, table/agg extraction, conflict grouping and
member retention under --top, effective-window reporting, degradation,
determinism, argument validation, and the loud stubs.

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
BASE_OPTS = dict(NO_OVERRIDES, days=90, days_requested=90, min_count=5,
                 min_users=2, top=500, emit_rejected=False)


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


def _identity(user="U", role="", warehouse="", query_tag="", sample="",
              is_dbt=False):
    return {"user": user, "role": role, "warehouse": warehouse,
            "query_tag": query_tag, "sample_text": sample, "is_dbt": is_dbt}


def _row(fp, user, n, sample, **kw):
    return dict({"FINGERPRINT": fp, "USER_NAME": user, "ROLE_NAME": "",
                 "WAREHOUSE_NAME": "", "QUERY_TAG": "", "N_EXECUTIONS": n,
                 "SAMPLE_TEXT": sample, "FIRST_SEEN": "", "LAST_SEEN": ""}, **kw)


def run():
    # ---- aggregated (warehouse-native fingerprint) path ----
    f = _findings(AGG_FIXTURE)
    assert f["source"] == "query_history"
    assert f["platform"] == "snowflake" and f["scope"] == "account_usage"
    assert f["thresholds"] == {"min_count": 5, "min_users": 2}
    assert f["window_days"] == 90 and "window_days_requested" not in f

    # all-ETL / all-dbt clusters excluded: counted, absent from clusters[]
    assert f["pools"] == {"bi_service": 4, "ad_hoc": 3, "excluded": 2,
                          "system": 0, "catalog": 0, "bi_chrome": 0}
    dropped = {"fp_etl_fivetran", "fp_dbt_test"}
    assert not dropped & {c["fingerprint"] for c in f["clusters"]}
    # admitted-only emission by default: fp_below_threshold is counted in
    # pools/coverage but not written; --emit-rejected restores it
    assert len(f["clusters"]) == 6
    fr_all = _findings(AGG_FIXTURE, "--emit-rejected")
    assert len(fr_all["clusters"]) == 7
    assert fr_all["clusters"][-1]["fingerprint"] == "fp_below_threshold"

    # pooling with evidence; native hash version carried through
    tab = _cluster(f, "fp_tableau_net")
    assert tab["pool"] == "bi_service"
    assert any("tableau" in e for e in tab["pool_evidence"])
    assert tab["fingerprint_versions"] == [1]
    assert tab["n_executions_bi"] == 365 and tab["n_executions_human"] == 0

    # mixed traffic: the dbt identity's executions (flagged is_dbt in-warehouse)
    # are subtracted and disclosed, NOT allowed to suppress the dashboard shape
    mixed = _cluster(f, "fp_mixed_daily")
    assert mixed["pool"] == "bi_service" and mixed["admitted"]
    assert mixed["n_executions"] == 30 and mixed["n_executions_excluded"] == 10
    assert mixed["users"] == ["TABLEAU_SVC"]
    assert any("excluded 10 execution(s)" in e and "dbt-stamped" in e
               for e in mixed["pool_evidence"])

    # QUERY_TAG is a classification dim (Sigma sets it; stronger than usernames)
    sigma = _cluster(f, "fp_sigma_tag")
    assert sigma["pool"] == "bi_service"
    assert any("query_tag" in e and "sigma" in e for e in sigma["pool_evidence"])

    # admission per traffic class; identity rows merge into cluster totals
    adhoc = _cluster(f, "fp_adhoc_netref")
    assert adhoc["pool"] == "ad_hoc" and adhoc["admitted"]
    assert adhoc["n_executions_human"] == 8 and adhoc["n_users_human"] == 2
    below = _cluster(fr_all, "fp_below_threshold")
    assert not below["admitted"]  # n=3 < 5; listed only under --emit-rejected

    # BI recurrence can't be padded with human executions: 1 BI + 4 human
    # executions is NOT a dashboard pattern (and human traffic must clear both
    # its own bars)
    pad = _findings_from_rows([
        _row("fp_pad", "TABLEAU_SVC", 1, "SELECT SUM(x) FROM T"),
        _row("fp_pad", "JANE", 2, "SELECT SUM(x) FROM T"),
        _row("fp_pad", "BOB", 2, "SELECT SUM(x) FROM T"),
    ], "--emit-rejected")
    padded = _cluster(pad, "fp_pad")
    assert padded["pool"] == "bi_service"  # provenance label
    assert padded["n_executions"] == 5     # combined, kept as context
    assert not padded["admitted"]          # bi=1<5 and human=4<5: neither class

    # table extraction: dotted names uppercased, CTE name not a table
    human = _cluster(f, "fp_human_sessions")
    assert human["tables"] == ["ANALYTICS.MART.DIM_CLIENTS",
                               "ANALYTICS.MART.FCT_SESSIONS"]
    assert human["admitted"] and human["n_users_human"] == 3

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
    assert all(c["admitted"] for c in f["clusters"])

    # degradation + coverage (counts only)
    assert f["unavailable"] == ["viewer_counts"]
    assert f["coverage"] == {"rows_in": 13, "clusters_total": 9,
                             "clusters_admitted": 6, "clusters_emitted": 6,
                             "conflict_groups": 1,
                             "conflict_groups_beyond_top": 0}

    # determinism: identical output on a second run
    assert json.dumps(f, sort_keys=True) == json.dumps(_findings(AGG_FIXTURE),
                                                       sort_keys=True)

    # ---- classification unit checks ----
    assert qhe._token_match("MODE_SVC", "mode")
    assert not qhe._token_match("MODELING_ANALYST", "mode")
    assert qhe._token_match("DBT_CLOUD", "dbt")
    assert not qhe._token_match("PRODBT", "dbt")
    klass, why = qhe.classify_identity(_identity(user="JANE"),
                                       dict(NO_OVERRIDES, bi_users=["jane"]))
    assert klass == "bi" and "listed in --bi-users" in why
    klass, _ = qhe.classify_identity(_identity(user="TABLEAU_SVC"),
                                     dict(NO_OVERRIDES, exclude_users=["tableau_svc"]))
    assert klass == "etl"
    # content/flag beats identity: warehouse is_dbt flag, or markers in the sample
    klass, _ = qhe.classify_identity(_identity(user="TABLEAU_SVC", is_dbt=True),
                                     NO_OVERRIDES)
    assert klass == "dbt"
    klass, _ = qhe.classify_identity(
        _identity(user="TABLEAU_SVC", sample='SELECT 1 /* {"app": "dbt"} */'),
        NO_OVERRIDES)
    assert klass == "dbt"
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
    rows = [_row("fp_wide", f"USER_{i:02d}", 1, "SELECT COUNT(*) FROM T")
            for i in range(24)]
    rows.append(_row("fp_wide", "ZZ_TABLEAU_SVC", 1, "SELECT COUNT(*) FROM T"))
    fw = _findings_from_rows(rows)
    wide = _cluster(fw, "fp_wide")
    assert wide["pool"] == "bi_service"       # classified before truncation
    assert wide["admitted"]                   # human class: 24 execs, 24 users
    assert len(wide["users"]) == 20            # truncated only in the output

    # ---- content-level demotion: system chrome, catalog polling, BI UI chrome
    # (chrome is chrome no matter which identity/warehouse ran it — Snowsight
    # traffic on a BI-named warehouse must not reach the admitted set) ----
    demo_rows = [
        _row("fp_chrome_call", "CHRIS", 900,
             "CALL SYSTEM$GET_RECENT_IN_APP_NOTIFICATIONS()",
             WAREHOUSE_NAME="LOOKER_WH"),
        _row("fp_chrome_ctx", "CHRIS", 40,
             "SELECT SYS_CONTEXT('SNOWFLAKE$SESSION', 'USABLE_ROLES_FAST')",
             WAREHOUSE_NAME="LOOKER_WH"),
        _row("fp_no_tables", "CHRIS", 30, "SELECT CURRENT_USER()",
             WAREHOUSE_NAME="LOOKER_WH"),
        _row("fp_catalog", "APP_SVC", 80,
             'select table_name from "PROD"."INFORMATION_SCHEMA"."TABLES"'),
        _row("fp_rowcount", "APP_SVC", 200,
             "SELECT COUNT(*) FROM (SELECT 1 FROM PROD.MART.FCT_X GROUP BY d)"),
        _row("fp_filterpop", "APP_SVC", 150,
             'SELECT "PAYER", COUNT("PAYER") AS "_count" '
             'FROM PROD.MART.FCT_X GROUP BY "PAYER"'),
        _row("fp_real", "APP_SVC", 500,
             "SELECT d, SUM(amount) FROM PROD.MART.FCT_X GROUP BY d"),
    ]
    fd = _findings_from_rows(demo_rows, "--emit-rejected",
                             "--bi-users", "app_svc")
    assert fd["pools"] == {"bi_service": 1, "ad_hoc": 0, "excluded": 0,
                           "system": 3, "catalog": 1, "bi_chrome": 2}
    sysc = _cluster(fd, "fp_chrome_call")
    assert sysc["pool"] == "system" and not sysc["admitted"]
    assert any("demoted to system pool" in e for e in sysc["pool_evidence"])
    assert any("looker" in e for e in sysc["pool_evidence"])  # provenance kept
    # the SNOWFLAKE$SESSION marker lives inside a string literal — demotion must
    # scan comment-stripped text with literals KEPT
    assert _cluster(fd, "fp_chrome_ctx")["pool"] == "system"
    nt = _cluster(fd, "fp_no_tables")
    assert nt["pool"] == "system"
    assert any("no table references" in e for e in nt["pool_evidence"])
    cat = _cluster(fd, "fp_catalog")
    assert cat["pool"] == "catalog" and not cat["admitted"]
    for fp in ("fp_rowcount", "fp_filterpop"):
        chrome = _cluster(fd, fp)
        assert chrome["pool"] == "bi_chrome" and not chrome["admitted"]
    real = _cluster(fd, "fp_real")
    assert real["pool"] == "bi_service" and real["admitted"]
    # default emission drops demoted clusters; pool accounting is unchanged
    fd_min = _findings_from_rows(demo_rows, "--bi-users", "app_svc")
    assert [c["fingerprint"] for c in fd_min["clusters"]] == ["fp_real"]
    assert fd_min["coverage"]["clusters_emitted"] == 1
    assert fd_min["pools"] == fd["pools"]

    # ---- identity census + unclassified-service-account flagging ----
    census_rows = [
        _row("fp_app_a", "ANALYTICS_APP", 800,
             "SELECT a, SUM(x) FROM P.M.F GROUP BY a",
             WAREHOUSE_NAME="ELT_WH", ROLE_NAME="APP_ROLE"),
        _row("fp_app_b", "ANALYTICS_APP", 700,
             "SELECT b, SUM(y) FROM P.M.F GROUP BY b",
             WAREHOUSE_NAME="ELT_WH", ROLE_NAME="APP_ROLE"),
        _row("fp_jane", "jane@acme.com", 600, "SELECT c FROM P.M.D"),
        _row("fp_tab", "TABLEAU_SVC", 50,
             "SELECT d, SUM(z) FROM P.M.F2 GROUP BY d"),
    ]
    fs = _findings_from_rows(census_rows)
    assert [e["user"] for e in fs["identity_census"]] == [
        "ANALYTICS_APP", "jane@acme.com", "TABLEAU_SVC"]
    app = fs["identity_census"][0]
    assert app["classes"] == ["human"] and app["n_executions"] == 1500
    assert app["n_shapes"] == 2 and app["warehouses"] == ["ELT_WH"]
    assert fs["identity_census"][2]["classes"] == ["bi"]
    # flagged: high-volume, human-classified, non-email username. jane (email ->
    # a person) and TABLEAU_SVC (already bi) are not. The agent asks the analyst
    # what ANALYTICS_APP is, then re-runs with --bi-users:
    assert fs["service_account_candidates"] == ["ANALYTICS_APP"]
    assert [c["fingerprint"] for c in fs["clusters"]] == ["fp_tab"]
    fs2 = _findings_from_rows(census_rows, "--bi-users", "analytics_app")
    assert {c["fingerprint"] for c in fs2["clusters"]} == {"fp_app_a",
                                                           "fp_app_b", "fp_tab"}
    assert fs2["service_account_candidates"] == []

    # ---- --top: admitted first; conflict members of emitted groups retained ----
    ft = _findings_from_rows([
        _row("fp_noise", "JANE", 100, "SELECT * FROM T1"),
        _row("fp_bi", "TABLEAU_SVC", 10, "SELECT COUNT(*) FROM T2"),
    ], "--top", "1")
    assert [c["fingerprint"] for c in ft["clusters"]] == ["fp_bi"]
    assert ft["coverage"]["clusters_total"] == 2

    fc = _findings(AGG_FIXTURE, "--top", "1")
    fps = [c["fingerprint"] for c in fc["clusters"]]
    assert fps[0] == "fp_tableau_net"
    assert set(fps) == {"fp_tableau_net", "fp_looker_gross", "fp_adhoc_netref"}
    assert len(fc["conflict_groups"]) == 1  # group intact, members force-kept

    # groups entirely beyond --top are dropped and counted
    fb = _findings_from_rows([
        _row("A1", "TABLEAU_SVC", 100, "SELECT SUM(a) FROM P"),
        _row("A2", "TABLEAU_SVC", 90, "SELECT SUM(b) FROM P"),
        _row("B1", "TABLEAU_SVC", 10, "SELECT SUM(c) FROM Q"),
        _row("B2", "TABLEAU_SVC", 9, "SELECT SUM(d) FROM Q"),
    ], "--top", "1")
    assert {c["fingerprint"] for c in fb["clusters"]} == {"A1", "A2"}
    assert len(fb["conflict_groups"]) == 1
    assert fb["coverage"]["conflict_groups_beyond_top"] == 1

    # ---- information_schema scope: native hash, honest effective window ----
    fi = _findings(AGG_FIXTURE, "--scope", "information_schema")
    assert fi["scope"] == "information_schema"
    assert fi["window_days"] == 7 and fi["window_days_requested"] == 90
    assert set(fi["unavailable"]) == {"viewer_counts", "window_beyond_7_days",
                                      "result_limit_pre_filter"}
    assert fi["pools"] == f["pools"]  # same normalization path as account_usage

    # an EMPTY fallback is success-shaped (exit 0, valid file) — the outcome
    # tripwire must say mining is still blocked, on stderr, loudly
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        fe = _findings_from_rows(
            [_row("fp_mine_only", "MCP_USER", 1, "SELECT a FROM P.M.T")],
            "--scope", "information_schema")
    assert fe["coverage"]["clusters_admitted"] == 0
    assert "BLOCKED" in err.getvalue()
    assert "grant handoff applies now" in err.getvalue()
    err = io.StringIO()  # non-empty fallback: no tripwire
    with contextlib.redirect_stderr(err):
        _findings(AGG_FIXTURE, "--scope", "information_schema")
    assert "BLOCKED" not in err.getvalue()

    # ---- client canonicalizer path (library path for hash-less platforms) ----
    fr = qhe.build_findings(qhe._load_rows(RAW_FIXTURE), "other", "raw", "client",
                            dict(BASE_OPTS, min_count=2))
    assert set(fr["unavailable"]) == {"viewer_counts", "query_parameterized_hash"}
    # two literal-differing queries collapse to ONE client fingerprint; the
    # dbt-stamped third execution of the same shape is flagged per ROW (not per
    # sample), so its exclusion is deterministic
    assert fr["coverage"]["rows_in"] == 4 and fr["coverage"]["clusters_total"] == 2
    merged = next(c for c in fr["clusters"] if c["n_executions"] == 2)
    assert merged["fingerprint_source"] == "client"
    assert merged["users"] == ["BOB", "JANE"] and merged["n_users"] == 2
    assert merged["n_executions_excluded"] == 1
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
    assert "query_parameterized_hash_version" in sql
    assert "GROUP BY 1, 2, 3, 4, 5, 6, 7" in sql
    # window-over-aggregate must be aliased; QUALIFY/ORDER BY use the alias
    # (Snowflake rejects it as a raw ORDER BY expression)
    assert "QUALIFY cluster_executions >= 2" in sql
    assert "ORDER BY cluster_executions DESC" in sql
    assert "ILIKE ANY" in sql and "DATEADD(day, -90," in sql

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        assert qhe.main(["--emit-sql", "--platform", "snowflake",
                         "--scope", "information_schema"]) == 0
    isql = buf.getvalue()
    assert "INFORMATION_SCHEMA.QUERY_HISTORY" in isql
    assert "query_parameterized_hash" in isql   # native hash used here too
    # capped window starts one hour INSIDE the 7-day retention boundary — the
    # table function rejects a range start exactly on it
    assert "DATEADD(hour, -167," in isql
    assert "BEFORE the outer" in isql           # RESULT_LIMIT pre-filter disclosed

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
