#!/usr/bin/env python3
"""Mine warehouse query history into a compact, *draft-only* .query-findings.json.

Two phases — the script NEVER touches the warehouse (SQL execution is the
interview agent's job, read-only, via the warehouse MCP):

  Phase A (emit the extraction SQL; run it via the warehouse MCP, save rows):
      python3 scripts/query_history_extract.py --emit-sql --platform snowflake
  Phase B (cluster the saved rows into findings):
      python3 scripts/query_history_extract.py --rows .query-history-rows.json \\
          --platform snowflake -o .query-findings.json

The interview agent (Stage 0) maps findings to interview questions and ACF stubs —
all `status: draft`, tagged `# query-history-derived (<fingerprint>)` — which the
analyst then confirms. NOTHING here is ground truth: the miner surfaces candidates
and conflicts; it never writes a definition. Recurrence-after-canonicalization
separates institutionalized logic (BI-service pool) from ad-hoc exploration; when
several clusters compute different aggregations over the same tables, that conflict
IS the interview question (`conflict_groups`), not an answer.

Platforms are a registry: snowflake is implemented; databricks / bigquery /
redshift / fabric are registered stubs that fail loudly (their history sources are
named so a contributor knows where to start). Each platform declares, per scope,
whether canonicalization happens in-warehouse (e.g. Snowflake
QUERY_PARAMETERIZED_HASH) or client-side (the regex canonicalizer here) — new
platforms reuse one of the two paths.

Stdlib-only. Both input and output files are transient bootstrap artifacts,
gitignored at the context repo root — raw SQL never reaches a committed file.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Conservative substring heuristics for pooling. Every match is recorded as
# `pool_evidence` so the agent can audit and the analyst can correct with the
# explicit --bi-*/--exclude-users overrides.
BI_PATTERNS = (
    "tableau", "looker", "sigma", "metabase", "powerbi", "power_bi", "mode",
    "hex", "superset", "preset", "qlik", "thoughtspot", "domo",
)
ETL_PATTERNS = ("fivetran", "dbt", "airflow", "dagster", "airbyte", "stitch")

# Content-level dbt evidence, checked on the RAW sample_text (the markers live in
# comments and scaffolding the canonicalizer strips): dbt stamps every query it
# executes with a JSON query comment ({"app": "dbt", ...}) and wraps tests in
# recognizable internal names. This catches dbt traffic even when the executing
# user doesn't look like an ETL account — dbt logic belongs to the dbt repo
# (dbt-findings.json), not to history mining. Caveat: the query comment sits at
# the tail, so the warehouse-side 8000-char truncation can drop it on very long
# queries; the user/role patterns above remain the first line of defense.
DBT_MARKER_RES = (
    re.compile(r'"app"\s*:\s*"dbt"', re.IGNORECASE),
    re.compile(r"\bdbt_internal_test\b", re.IGNORECASE),
    re.compile(r"__dbt__cte__", re.IGNORECASE),
)


def dbt_markers(text):
    """-> the dbt content markers found in text (empty list = none)."""
    return [rx.pattern for rx in DBT_MARKER_RES if rx.search(text or "")]

AGG_RE = re.compile(
    r"\b(sum|count|avg|min|max|median|approx_\w+)\s*\(\s*([^()]*?)\s*\)",
    re.IGNORECASE,
)
# Dotted, optionally quoted identifier after FROM/JOIN. Subqueries don't match
# (they start with a paren). Known misses, acceptable for a hint: LATERAL views,
# table functions (TABLE(...)), UNNEST. If sqlglot is ever adopted, this and the
# canonicalizer are the two functions to replace — tables[] stays a hint the
# agent cross-checks, never authoritative.
TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+((?:\"[^\"]+\"|[A-Za-z_][\w$]*)"
    r"(?:\.(?:\"[^\"]+\"|[A-Za-z_][\w$]*)){0,2})",
    re.IGNORECASE,
)
CTE_RE = re.compile(r"\b([A-Za-z_][\w$]*)\s+AS\s*\(", re.IGNORECASE)
COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
STRING_LIT_RE = re.compile(r"'(?:[^']|'')*'")
NUMBER_LIT_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
IN_LIST_RE = re.compile(r"\bin\s*\(\s*\?(?:\s*,\s*\?)*\s*\)")

MAX_SAMPLE_CHARS = 4000
MAX_LIST_ENTRIES = 20


def _warn(msg):
    print(f"query_history_extract: WARNING: {msg}", file=sys.stderr)


def _die(msg, code=2):
    print(f"query_history_extract: {msg}", file=sys.stderr)
    sys.exit(code)


# ----- Snowflake ---------------------------------------------------------------

def _sf_emit_account_usage(days, limit):
    return f"""\
-- Query-history extraction (Snowflake, ACCOUNT_USAGE scope; {days}-day window).
-- Requires imported privileges on the SNOWFLAKE database (an ACCOUNTADMIN grants
-- them: GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <role>).
-- ACCOUNT_USAGE lags ~45min-3h — fine for mining. 365-day retention.
-- On "Object does not exist or not authorized": re-run --emit-sql with
--   --scope information_schema (7-day window, no privileges needed).
-- Run read-only via the warehouse MCP; save the result rows VERBATIM as JSON to
-- .query-history-rows.json at the context repo root (gitignored).
SELECT
  query_parameterized_hash              AS fingerprint,
  COUNT(*)                              AS n_executions,
  COUNT(DISTINCT user_name)             AS n_users,
  ARRAY_AGG(DISTINCT user_name)         AS users,
  ARRAY_AGG(DISTINCT role_name)         AS roles,
  ARRAY_AGG(DISTINCT warehouse_name)    AS warehouses,
  LEFT(ANY_VALUE(query_text), 8000)     AS sample_text,
  MIN(start_time)                       AS first_seen,
  MAX(start_time)                       AS last_seen
FROM snowflake.account_usage.query_history
WHERE start_time >= DATEADD(day, -{days}, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND query_type = 'SELECT'
  AND query_parameterized_hash IS NOT NULL
GROUP BY 1
HAVING COUNT(*) >= 2
ORDER BY n_executions DESC
LIMIT {limit}"""


def _sf_emit_information_schema(days, limit):
    days = min(days, 7)
    limit = min(limit, 10000)
    return f"""\
-- Query-history extraction (Snowflake, INFORMATION_SCHEMA fallback).
-- No special privileges, but: 7-day window max, visibility limited to queries
-- your role can see, and NO query_parameterized_hash (the script canonicalizes
-- client-side instead). Prefer --scope account_usage when privileges allow.
-- Run read-only via the warehouse MCP; save the result rows VERBATIM as JSON to
-- .query-history-rows.json at the context repo root (gitignored).
SELECT
  query_text,
  user_name,
  role_name,
  warehouse_name,
  start_time
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
    END_TIME_RANGE_START => DATEADD(day, -{days}, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => {limit}))
WHERE execution_status = 'SUCCESS'
  AND query_type = 'SELECT'"""


def _stub(history_source):
    return {"stub": history_source}


PLATFORMS = {
    "snowflake": {
        "scopes": {
            # canonicalizer "warehouse": rows arrive pre-aggregated per fingerprint.
            # canonicalizer "client": rows arrive raw; we canonicalize + group here.
            "account_usage": {"emit_sql": _sf_emit_account_usage,
                              "canonicalizer": "warehouse"},
            "information_schema": {"emit_sql": _sf_emit_information_schema,
                                   "canonicalizer": "client"},
        },
        "default_scope": "account_usage",
    },
    "databricks": _stub("system.query.history"),
    "bigquery": _stub("region-qualified INFORMATION_SCHEMA.JOBS "
                      "(no param hash — reuse the client-side canonicalizer)"),
    "redshift": _stub("SYS_QUERY_HISTORY / STL_QUERY"),
    "fabric": _stub("queryinsights views"),
}


def _resolve_platform(name, scope):
    entry = PLATFORMS.get(name)
    if entry is None:
        _die(f"unknown platform '{name}'. Registered: {', '.join(sorted(PLATFORMS))}")
    if "stub" in entry:
        implemented = sorted(k for k, v in PLATFORMS.items() if "stub" not in v)
        _die(f"'{name}' is registered but not implemented — its history source is "
             f"{entry['stub']}; contributions welcome. "
             f"Implemented: {', '.join(implemented)}.")
    scope = scope or entry["default_scope"]
    if scope not in entry["scopes"]:
        _die(f"unknown scope '{scope}' for {name}. "
             f"Scopes: {', '.join(sorted(entry['scopes']))}")
    return entry["scopes"][scope], scope


# ----- client-side canonicalization (platforms/scopes without a warehouse hash) --

def _strip_comments(text):
    return COMMENT_RE.sub(" ", text or "")


def canonicalize(text):
    """Literal-stripping canonical form: the client-side stand-in for Snowflake's
    QUERY_PARAMETERIZED_HASH. Two queries differing only in literal values (or
    IN-list length) collapse to the same form."""
    t = _strip_comments(text)
    t = STRING_LIT_RE.sub("?", t)
    t = NUMBER_LIT_RE.sub("?", t)
    t = t.lower()
    t = IN_LIST_RE.sub("in (?)", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _client_fingerprint(text):
    return hashlib.sha256(canonicalize(text).encode()).hexdigest()[:16]


# ----- SQL feature extraction (hints, never authoritative) -----------------------

def extract_tables(text):
    """FROM/JOIN targets, minus CTE names, uppercased (quoted parts keep case)."""
    t = _strip_comments(text)
    ctes = {m.group(1).upper() for m in CTE_RE.finditer(t)}
    tables = set()
    for m in TABLE_RE.finditer(t):
        ident = m.group(1)
        parts = [p if p.startswith('"') else p.upper() for p in ident.split(".")]
        if len(parts) == 1 and (parts[0] in ctes or parts[0] in ("TABLE", "LATERAL",
                                                                 "UNNEST")):
            continue
        tables.add(".".join(parts))
    return sorted(tables)


def agg_signatures(text):
    """Normalized aggregate calls, e.g. 'sum(collected_amount)'. Nested-paren
    arguments don't match — the aggregate still registers via inner calls."""
    t = re.sub(r"\s+", " ", _strip_comments(text)).lower()
    return sorted({f"{m.group(1)}({m.group(2).strip()})" for m in AGG_RE.finditer(t)})


# ----- pooling -------------------------------------------------------------------

def _csv(arg):
    return [s.strip().lower() for s in (arg or "").split(",") if s.strip()]


def classify_pool(users, roles, warehouses, opts):
    """-> (pool, evidence[]). Explicit overrides beat heuristics; exclusion beats BI
    (an ETL user is never a definition source, even on a BI warehouse)."""
    dims = (("user", users), ("role", roles), ("warehouse", warehouses))
    evidence = []
    for kind, values in dims:
        for v in values:
            if v.lower() in opts["exclude_users"] and kind == "user":
                return "excluded", [f"user '{v}' listed in --exclude-users"]
    for kind, values in dims:
        for v in values:
            for pat in ETL_PATTERNS:
                if pat in v.lower():
                    return "excluded", [f"{kind} '{v}' matched etl pattern '{pat}'"]
    for kind, values, listed in (("user", users, opts["bi_users"]),
                                 ("role", roles, opts["bi_roles"]),
                                 ("warehouse", warehouses, opts["bi_warehouses"])):
        for v in values:
            if v.lower() in listed:
                evidence.append(f"{kind} '{v}' listed in --bi-{kind}s")
    for kind, values in dims:
        for v in values:
            for pat in BI_PATTERNS:
                if pat in v.lower():
                    evidence.append(f"{kind} '{v}' matched bi pattern '{pat}'")
    if evidence:
        return "bi_service", evidence
    return "ad_hoc", []


# ----- row normalization ---------------------------------------------------------

def _load_rows(path):
    doc = json.loads(Path(path).read_text())
    rows = doc.get("rows") if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        _die(f"{path}: expected a JSON array of rows or {{\"rows\": [...]}}")
    return [{str(k).lower(): v for k, v in r.items()} for r in rows if isinstance(r, dict)]


def _as_list(v):
    """Tolerate MCP result quirks: a real array, a JSON-encoded array string, a
    bare scalar, or null."""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x is not None]
    if isinstance(v, str) and v.strip().startswith("["):
        try:
            return [str(x) for x in json.loads(v) if x is not None]
        except (ValueError, TypeError):
            pass
    return [str(v)]


def clusters_from_aggregated(rows):
    """Warehouse-canonicalized rows (one row per fingerprint) -> raw clusters."""
    out = []
    for r in rows:
        if not r.get("fingerprint"):
            continue
        out.append({
            "fingerprint": str(r["fingerprint"]),
            "fingerprint_source": "warehouse",
            "sample_text": (r.get("sample_text") or "")[:MAX_SAMPLE_CHARS],
            "n_executions": int(r.get("n_executions") or 0),
            "n_users": int(r.get("n_users") or 0),
            "users": sorted(set(_as_list(r.get("users"))))[:MAX_LIST_ENTRIES],
            "roles": sorted(set(_as_list(r.get("roles"))))[:MAX_LIST_ENTRIES],
            "warehouses": sorted(set(_as_list(r.get("warehouses"))))[:MAX_LIST_ENTRIES],
            "first_seen": str(r.get("first_seen") or ""),
            "last_seen": str(r.get("last_seen") or ""),
        })
    return out


def clusters_from_raw(rows):
    """Raw per-query rows -> raw clusters via the client canonicalizer."""
    by_fp = {}
    for r in rows:
        text = r.get("query_text")
        if not text:
            continue
        fp = _client_fingerprint(text)
        c = by_fp.setdefault(fp, {
            "fingerprint": fp, "fingerprint_source": "client",
            "sample_text": text[:MAX_SAMPLE_CHARS], "n_executions": 0,
            "users": set(), "roles": set(), "warehouses": set(),
            "first_seen": "", "last_seen": "",
        })
        c["n_executions"] += 1
        for key, col in (("users", "user_name"), ("roles", "role_name"),
                         ("warehouses", "warehouse_name")):
            if r.get(col):
                c[key].add(str(r[col]))
        ts = str(r.get("start_time") or "")
        if ts:
            c["first_seen"] = min(filter(None, [c["first_seen"], ts]))
            c["last_seen"] = max(c["last_seen"], ts)
    out = []
    for c in by_fp.values():
        c["n_users"] = len(c["users"])
        for key in ("users", "roles", "warehouses"):
            c[key] = sorted(c[key])[:MAX_LIST_ENTRIES]
        out.append(c)
    return out


# ----- conflict groups -----------------------------------------------------------

def find_conflict_groups(clusters):
    """Admitted, aggregate-shaped clusters sharing an identical table set. 2-8
    distinct members = a conflict candidate the interview adjudicates; more is
    just a hot table (a coverage fact, not a conflict). The script deliberately
    does NOT judge whether two calculations target the same metric — that
    semantic call belongs to the interviewing agent and the analyst."""
    by_tables = {}
    for c in clusters:
        if not c["admitted"] or not c["tables"] or not c["agg_signatures"]:
            continue
        by_tables.setdefault(tuple(c["tables"]), []).append(c)
    groups = []
    for tables in sorted(by_tables):
        members = sorted(by_tables[tables], key=lambda c: (-c["n_executions"],
                                                           c["fingerprint"]))
        if not 2 <= len(members) <= 8:
            continue
        short = tables[0].split(".")[-1].strip('"').lower()
        gid = f"cg_{short}_{len(groups) + 1}"
        for m in members:
            m["conflict_group"] = gid
        groups.append({
            "id": gid,
            "tables": list(tables),
            "members": [m["fingerprint"] for m in members],
            "agg_signatures": {m["fingerprint"]: m["agg_signatures"]
                               for m in members},
        })
    return groups


# ----- assembly ------------------------------------------------------------------

def build_findings(rows, platform, scope, canonicalizer, opts):
    raw = (clusters_from_aggregated(rows) if canonicalizer == "warehouse"
           else clusters_from_raw(rows))

    pools = {"bi_service": 0, "ad_hoc": 0, "excluded": 0}
    clusters = []
    for c in raw:
        if dbt_markers(c["sample_text"]):
            # Content beats identity: a dbt-stamped query is dbt-generated no
            # matter who ran it, and its logic already reaches the interview via
            # dbt extraction — keeping it here would double-count the same info.
            pools["excluded"] += 1
            continue
        pool, evidence = classify_pool(c["users"], c["roles"], c["warehouses"], opts)
        pools[pool] += 1
        if pool == "excluded":
            continue  # ETL/orchestration noise: counted, never a candidate
        if pool == "bi_service":
            # One service user fronts all dashboard viewers, so the distinct-
            # consumer test can't apply here (see unavailable: viewer_counts).
            admitted = c["n_executions"] >= opts["min_count"]
        else:
            admitted = (c["n_executions"] >= opts["min_count"]
                        and c["n_users"] >= opts["min_users"])
        c.update({
            "pool": pool,
            "pool_evidence": evidence,
            "admitted": admitted,
            "tables": extract_tables(c["sample_text"]),
            "agg_signatures": agg_signatures(c["sample_text"]),
            "conflict_group": None,
        })
        clusters.append(c)

    clusters.sort(key=lambda c: (-c["n_executions"], c["fingerprint"]))
    clusters = clusters[:opts["top"]]
    conflict_groups = find_conflict_groups(clusters)

    unavailable = ["viewer_counts"]  # pushdown reality; BI-API enrichment slot
    if canonicalizer == "client":
        unavailable += ["query_parameterized_hash", "window_beyond_7_days"]

    return {
        "source": "query_history",
        "platform": platform,
        "scope": scope,
        "window_days": opts["days"],
        "thresholds": {"min_count": opts["min_count"], "min_users": opts["min_users"]},
        "clusters": clusters,
        "conflict_groups": conflict_groups,
        "pools": pools,
        "unavailable": unavailable,
        "coverage": {
            "rows_in": len(rows),
            "clusters_total": len(raw),
            "clusters_admitted": sum(1 for c in clusters if c["admitted"]),
            "conflict_groups": len(conflict_groups),
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--emit-sql", action="store_true",
                   help="print the platform's history-extraction SQL and exit")
    g.add_argument("--rows", help="path to saved result rows (JSON array or "
                                  "{\"rows\": [...]}; keys any case)")
    ap.add_argument("--platform", required=True,
                    help=f"warehouse platform ({', '.join(sorted(PLATFORMS))})")
    ap.add_argument("--scope", help="history source scope (platform-specific; "
                                    "snowflake: account_usage | information_schema)")
    ap.add_argument("--days", type=int, default=90, help="lookback window (default 90)")
    ap.add_argument("--limit", type=int, default=5000,
                    help="in-warehouse row cap for --emit-sql (default 5000)")
    ap.add_argument("--bi-users", default="", help="CSV of known BI service users")
    ap.add_argument("--bi-roles", default="", help="CSV of known BI roles")
    ap.add_argument("--bi-warehouses", default="", help="CSV of known BI warehouses")
    ap.add_argument("--exclude-users", default="",
                    help="CSV of users to exclude (ETL/orchestration)")
    ap.add_argument("--min-count", type=int, default=5,
                    help="min executions for a cluster to be admitted (default 5)")
    ap.add_argument("--min-users", type=int, default=2,
                    help="min distinct users for an AD-HOC cluster (default 2; "
                         "not applied to bi_service — one service user fronts "
                         "all viewers)")
    ap.add_argument("--top", type=int, default=500,
                    help="max clusters emitted (default 500)")
    ap.add_argument("-o", "--out", help="write JSON here instead of stdout")
    args = ap.parse_args(argv)

    scope_entry, scope = _resolve_platform(args.platform, args.scope)

    if args.emit_sql:
        print(scope_entry["emit_sql"](args.days, args.limit))
        return 0

    opts = {
        "days": args.days, "min_count": args.min_count, "min_users": args.min_users,
        "top": args.top,
        "bi_users": _csv(args.bi_users), "bi_roles": _csv(args.bi_roles),
        "bi_warehouses": _csv(args.bi_warehouses),
        "exclude_users": _csv(args.exclude_users),
    }
    findings = build_findings(_load_rows(args.rows), args.platform, scope,
                              scope_entry["canonicalizer"], opts)

    text = json.dumps(findings, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
