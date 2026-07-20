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

Operational chrome is demoted by CONTENT, not identity: console/system calls and
no-table queries (`system` pool), catalog polling (`catalog`), and BI UI
scaffolding like row-count wrappers (`bi_chrome`) are counted and disclosed but
never admitted — dogfooding showed Snowsight traffic riding a BI-named warehouse
otherwise dominates the admitted set. The findings also carry an
`identity_census` plus `service_account_candidates` (high-volume identities that
defaulted to "human"): the agent asks the analyst what they are and re-runs with
--bi-users / --exclude-users — the miner never guesses. Only admitted clusters
(plus force-kept conflict-group members) are emitted unless --emit-rejected.

The extraction SQL returns one row per (query shape x executing identity x dbt
flag), so a shape shared by a dashboard, a human, and an ETL job is accounted
per traffic class: BI and human executions are counted separately (each must
qualify on its own for admission), and ETL/dbt executions are subtracted and
disclosed (`n_executions_excluded`, `pool_evidence`) instead of suppressing the
whole shape.

Platforms are a registry: snowflake is implemented; databricks / bigquery /
redshift / fabric are registered stubs that fail loudly (their history sources are
named so a contributor knows where to start). Each platform declares, per scope,
whether canonicalization happens in-warehouse (Snowflake's
QUERY_PARAMETERIZED_HASH — both scopes) or client-side (the lexer + regex
canonicalizer here, for platforms without a native hash) — new platforms reuse
one of the two paths.

Stdlib-only. Both input and output files are transient bootstrap artifacts,
gitignored at the context repo root — raw SQL never reaches a committed file.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Conservative heuristics for classifying an executing identity, token-boundary
# matched (so "mode" matches MODE_SVC but not MODELING_ANALYST). Every match is
# recorded as `pool_evidence` so the agent can audit and the analyst can correct
# with the explicit --bi-*/--exclude-users overrides.
BI_PATTERNS = (
    "tableau", "looker", "sigma", "metabase", "powerbi", "power_bi", "mode",
    "hex", "superset", "preset", "qlik", "thoughtspot", "domo",
)
ETL_PATTERNS = ("fivetran", "dbt", "airflow", "dagster", "airbyte", "stitch")

# Content-level dbt evidence: dbt stamps every query it executes with a JSON query
# comment ({"app": "dbt", ...}) and wraps tests in recognizable internal names.
# The parameterized hash IGNORES comments, so stamped and unstamped executions of
# the same shape share a fingerprint — which is why the emitted SQL computes a
# per-execution `is_dbt` flag and groups on it (a sampled query text would make
# the subtraction nondeterministic). These regexes are the client-side fallback
# for raw rows and a belt-and-braces check on samples; they run on RAW text (the
# markers live in comments the canonicalizer strips).
DBT_MARKER_RES = (
    re.compile(r'"app"\s*:\s*"dbt"', re.IGNORECASE),
    re.compile(r"\bdbt_internal_test\b", re.IGNORECASE),
    re.compile(r"__dbt__cte__", re.IGNORECASE),
)
# Keep in sync with DBT_MARKER_RES — the same three markers, as ILIKE patterns
# for the emitted SQL's is_dbt column.
DBT_MARKER_ILIKE = "('%\"app\": \"dbt\"%', '%dbt_internal_test%', '%__dbt__cte__%')"


def dbt_markers(text):
    """-> the dbt content markers found in text (empty list = none)."""
    return [rx.pattern for rx in DBT_MARKER_RES if rx.search(text or "")]


AGG_RE = re.compile(
    r"\b(sum|count|avg|min|max|median|approx_\w+)\s*\(\s*([^()]*?)\s*\)",
    re.IGNORECASE,
)
# Dotted, optionally quoted identifier after FROM/JOIN, applied to lexer-scrubbed
# text (strings already replaced), so literals can't fake a table. Subqueries
# don't match (they start with a paren). Known misses, acceptable for a hint:
# LATERAL views, table functions (TABLE(...)), UNNEST, and nested-aggregate
# arguments like SUM(COALESCE(x, 0)) (the inner call still registers). If sqlglot
# is ever adopted, these regexes and the canonicalizer are what it replaces —
# tables[] stays a hint the agent cross-checks, never authoritative.
TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+((?:\"[^\"]+\"|[A-Za-z_][\w$]*)"
    r"(?:\.(?:\"[^\"]+\"|[A-Za-z_][\w$]*)){0,2})",
    re.IGNORECASE,
)
CTE_RE = re.compile(r"\b([A-Za-z_][\w$]*)\s+AS\s*\(", re.IGNORECASE)
NUMBER_LIT_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
IN_LIST_RE = re.compile(r"\bin\s*\(\s*\?(?:\s*,\s*\?)*\s*\)")

# Console/session chrome, matched on comment-stripped raw text with string
# literals KEPT (SYS_CONTEXT('SNOWFLAKE$SESSION', ...) hides its marker inside a
# literal, which canonicalize() would erase). Content-level on purpose: Snowsight
# runs on whatever warehouse the session holds, so this traffic otherwise
# inherits a bi_service classification from a BI-named warehouse.
SYSTEM_TEXT_RES = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"^\s*call\b",
    r"\bsystem\$",
    r"\bsnowflake\$session\b",
    r"\bis_database_role_in_session\s*\(",
    r"\bis_application_role_in_session\s*\(",
    r"\bcurrent_available_roles\s*\(",
    r"\bresult_scan\s*\(",
    r"\bget_ddl\s*\(",
    r"\bentity_detail\s*\(",
))
# BI UI scaffolding, matched on the canonicalized text: row-count wrappers
# (pagination) and filter-value population. These recur at dashboard volume but
# carry no metric logic — without demotion, one embedded-analytics service user
# floods the admitted set with them.
BI_CHROME_RES = (
    re.compile(r"^select count\((?:\*|\?)\) from \("),
    re.compile(r'count\("?[\w$]+"?\) as "_count"'),
)

MAX_SAMPLE_CHARS = 4000
MAX_LIST_ENTRIES = 20


def _warn(msg):
    print(f"query_history_extract: WARNING: {msg}", file=sys.stderr)


def _die(msg, code=2):
    print(f"query_history_extract: {msg}", file=sys.stderr)
    sys.exit(code)


# ----- Snowflake ---------------------------------------------------------------

_SF_SELECT_BODY = f"""\
SELECT
  query_parameterized_hash              AS fingerprint,
  query_parameterized_hash_version      AS fingerprint_version,
  user_name,
  role_name,
  warehouse_name,
  query_tag,
  (query_text ILIKE ANY {DBT_MARKER_ILIKE}) AS is_dbt,
  COUNT(*)                              AS n_executions,
  SUM(COUNT(*)) OVER (PARTITION BY query_parameterized_hash)
                                        AS cluster_executions,
  LEFT(ANY_VALUE(query_text), 8000)     AS sample_text,
  MIN(start_time)                       AS first_seen,
  MAX(start_time)                       AS last_seen"""

# QUALIFY and ORDER BY reference the cluster_executions ALIAS — Snowflake rejects
# a window-over-aggregate written directly as an ORDER BY expression.
_SF_GROUP_TAIL = """\
GROUP BY 1, 2, 3, 4, 5, 6, 7
QUALIFY cluster_executions >= 2
ORDER BY cluster_executions DESC, n_executions DESC
LIMIT {limit}"""


def _sf_emit_account_usage(days, limit):
    return f"""\
-- Query-history extraction (Snowflake, ACCOUNT_USAGE scope; {days}-day window).
-- The executing user needs ACCOUNT_USAGE access. Least-privilege grant (run as
-- ACCOUNTADMIN; <USER> = the MCP user, <WAREHOUSE> = its warehouse):
--   CREATE ROLE IF NOT EXISTS QUERY_HISTORY_READER;
--   GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE QUERY_HISTORY_READER;
--   GRANT USAGE ON WAREHOUSE <WAREHOUSE> TO ROLE QUERY_HISTORY_READER;
--   GRANT ROLE QUERY_HISTORY_READER TO USER <USER>;
-- ACCOUNT_USAGE lags ~45min-3h — fine for mining. 365-day retention.
-- On "Object does not exist or not authorized": (1) hand the analyst the
--   forwardable admin-grant note NOW (privilege playbook in
--   query-history-extraction.md) — it needs another human with hours-to-days
--   of turnaround, so it starts first; (2) meanwhile re-run --emit-sql with
--   --scope information_schema (7-day window, no privileges needed) — a
--   stopgap, not a substitute.
-- One row per (query shape x identity x dbt flag), so mixed traffic on the same
-- shape is counted per class; LIMIT caps identity-rows, not shapes.
-- Run read-only via the warehouse MCP; save the result rows VERBATIM as JSON to
-- .query-history-rows.json at the context repo root (gitignored).
{_SF_SELECT_BODY}
FROM snowflake.account_usage.query_history
WHERE start_time >= DATEADD(day, -{days}, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND query_type = 'SELECT'
  AND query_parameterized_hash IS NOT NULL
{_SF_GROUP_TAIL.format(limit=limit)}"""


def _sf_emit_information_schema(days, limit):
    limit = min(limit, 10000)
    # Start one hour INSIDE the retention boundary: the table function rejects a
    # range start that touches it ("Cannot retrieve data from more than 7 days
    # ago"), and DATEADD(day, -7, CURRENT_TIMESTAMP()) is exactly on it.
    hours = days * 24 - 1
    return f"""\
-- Query-history extraction (Snowflake, INFORMATION_SCHEMA fallback; {days}-day window).
-- No special privileges, but: 7-day window max, and visibility limited to queries
-- your role can see. The native query_parameterized_hash IS available here too.
-- NOTE: RESULT_LIMIT is applied by the table function BEFORE the outer
-- SUCCESS/SELECT filters, so {limit} history entries may yield fewer relevant
-- rows. Prefer --scope account_usage when privileges allow.
-- Run read-only via the warehouse MCP; save the result rows VERBATIM as JSON to
-- .query-history-rows.json at the context repo root (gitignored).
{_SF_SELECT_BODY}
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
    END_TIME_RANGE_START => DATEADD(hour, -{hours}, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => {limit}))
WHERE execution_status = 'SUCCESS'
  AND query_type = 'SELECT'
  AND query_parameterized_hash IS NOT NULL
{_SF_GROUP_TAIL.format(limit=limit)}"""


def _stub(history_source):
    return {"stub": history_source}


PLATFORMS = {
    "snowflake": {
        "scopes": {
            # Both scopes aggregate in-warehouse on the native parameterized hash
            # (canonicalizer "warehouse"). canonicalizer "client" is the library
            # path for platforms without a native hash: raw rows, canonicalized
            # and grouped here. max_days caps the effective window; "unavailable"
            # is what the scope can never provide (disclosed in findings).
            "account_usage": {"emit_sql": _sf_emit_account_usage,
                              "canonicalizer": "warehouse", "max_days": None,
                              "unavailable": []},
            "information_schema": {"emit_sql": _sf_emit_information_schema,
                                   "canonicalizer": "warehouse", "max_days": 7,
                                   "unavailable": ["window_beyond_7_days",
                                                   "result_limit_pre_filter"]},
        },
        "default_scope": "account_usage",
    },
    "databricks": _stub("system.query.history"),
    "bigquery": _stub("region-qualified INFORMATION_SCHEMA.JOBS "
                      "(no native hash — reuse the client-side canonicalizer)"),
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


# ----- SQL scrubbing (single-pass lexer, stdlib) ---------------------------------

def scrub_sql(text, replace_strings=True):
    """Remove -- and /* */ comments and (optionally) replace single-quoted string
    literals with ?, in ONE pass that respects nesting: a '--' inside a literal is
    not a comment, a quote inside a comment is not a string, '' escapes stay inside
    their literal. Double-quoted identifiers pass through untouched. This is what
    keeps regex feature-extraction from matching SQL-looking text inside literals."""
    out = []
    i, n = 0, len(text or "")
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "-" and nxt == "-":
            j = text.find("\n", i)
            out.append(" ")
            i = n if j < 0 else j  # keep the newline itself
        elif ch == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            out.append(" ")
            i = n if j < 0 else j + 2
        elif ch == "'":
            j = i + 1
            while j < n:
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        j += 2  # '' escape, still inside the literal
                        continue
                    break
                j += 1
            out.append("?" if replace_strings else text[i:min(j + 1, n)])
            i = min(j + 1, n)
        elif ch == '"':
            j = text.find('"', i + 1)
            j = n - 1 if j < 0 else j
            out.append(text[i:j + 1])
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def canonicalize(text):
    """Literal-stripping canonical form: the client-side stand-in for a native
    parameterized hash. Two queries differing only in literal values (or IN-list
    length) collapse to the same form."""
    t = scrub_sql(text, replace_strings=True)
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
    t = scrub_sql(text, replace_strings=True)
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
    """Normalized aggregate calls, e.g. 'sum(collected_amount)'."""
    t = re.sub(r"\s+", " ", scrub_sql(text, replace_strings=True)).lower()
    return sorted({f"{m.group(1)}({m.group(2).strip()})" for m in AGG_RE.finditer(t)})


def _is_catalog_relation(table):
    parts = [p.strip('"').upper() for p in table.split(".")]
    return "INFORMATION_SCHEMA" in parts or parts[0] == "SNOWFLAKE"


def classify_noise(sample_text, tables):
    """-> (demoted pool, why) when a cluster's SHAPE is operational chrome rather
    than analytics, else None. Ordered most- to least-specific; the demotion is
    disclosed in pool_evidence and the cluster stays counted in pools{}."""
    scrubbed = scrub_sql(sample_text or "", replace_strings=False).lower()
    for rx in SYSTEM_TEXT_RES:
        if rx.search(scrubbed):
            return "system", f"demoted to system pool: matched '{rx.pattern}'"
    if not tables:
        return "system", "demoted to system pool: no table references"
    if all(_is_catalog_relation(t) for t in tables):
        return "catalog", ("demoted to catalog pool: reads only "
                           "catalog/metadata relations")
    canon = canonicalize(sample_text or "")
    for rx in BI_CHROME_RES:
        if rx.search(canon):
            return "bi_chrome", f"demoted to bi_chrome pool: matched '{rx.pattern}'"
    return None


# ----- per-identity classification ------------------------------------------------

def _csv(arg):
    return [s.strip().lower() for s in (arg or "").split(",") if s.strip()]


def _token_match(name, pattern):
    """Token-boundary substring match: 'mode' hits MODE_SVC, not MODELING_ANALYST;
    'dbt' hits DBT_CLOUD, not PRODBT. Underscores and punctuation are boundaries."""
    return re.search(rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])",
                     (name or "").lower()) is not None


def classify_identity(ident, opts):
    """-> (traffic class, evidence). Classes: 'dbt' | 'etl' (both dropped),
    'bi' | 'human' (both kept, counted separately). Precedence: the warehouse-
    computed is_dbt flag / content markers beat identity (a dbt-stamped query is
    dbt-generated no matter who ran it), explicit exclusion beats explicit BI,
    explicit lists beat pattern heuristics."""
    who = f"user '{ident['user']}'" if ident["user"] else "unknown user"
    if ident.get("is_dbt") or dbt_markers(ident["sample_text"]):
        return "dbt", f"{who}: dbt-stamped query text"
    if ident["user"].lower() in opts["exclude_users"]:
        return "etl", f"{who} listed in --exclude-users"
    dims = (("user", ident["user"]), ("role", ident["role"]),
            ("warehouse", ident["warehouse"]), ("query_tag", ident["query_tag"]))
    for kind, v in dims:
        for pat in ETL_PATTERNS:
            if v and _token_match(v, pat):
                return "etl", f"{kind} '{v}' matched etl pattern '{pat}'"
    for kind, v, listed in (("user", ident["user"], opts["bi_users"]),
                            ("role", ident["role"], opts["bi_roles"]),
                            ("warehouse", ident["warehouse"], opts["bi_warehouses"])):
        if v and v.lower() in listed:
            return "bi", f"{kind} '{v}' listed in --bi-{kind}s"
    for kind, v in dims:
        for pat in BI_PATTERNS:
            if v and _token_match(v, pat):
                return "bi", f"{kind} '{v}' matched bi pattern '{pat}'"
    return "human", None


def identity_census(ident_rows, opts):
    """-> (census, service_account_candidates). The census aggregates identity
    rows per user with their traffic classification. Candidates are users whose
    HUMAN-classified volume says 'unrecognized service account' (>= max(100, 5%
    of window executions), username not email-shaped): the single biggest miss in
    dogfooding was an app service user defaulting to human, whose one identity
    can never clear min_users. The miner only flags — the agent asks the analyst
    and re-runs with --bi-users / --exclude-users."""
    by_user = {}
    for ident in ident_rows:
        user = ident["user"]
        if not user:
            continue
        klass, _ = classify_identity(ident, opts)
        e = by_user.setdefault(user, {"user": user, "fps": set(),
                                      "n_executions": 0,
                                      "n_executions_by_class": {},
                                      "warehouses": set(), "roles": set()})
        e["fps"].add(ident["fingerprint"])
        e["n_executions"] += ident["n_executions"]
        by_class = e["n_executions_by_class"]
        by_class[klass] = by_class.get(klass, 0) + ident["n_executions"]
        if ident["warehouse"]:
            e["warehouses"].add(ident["warehouse"])
        if ident["role"]:
            e["roles"].add(ident["role"])
    census = []
    for user in sorted(by_user, key=lambda u: (-by_user[u]["n_executions"], u)):
        e = by_user[user]
        census.append({
            "user": user,
            "classes": sorted(e["n_executions_by_class"]),
            "n_executions": e["n_executions"],
            "n_executions_by_class": e["n_executions_by_class"],
            "n_shapes": len(e["fps"]),
            "warehouses": sorted(e["warehouses"])[:MAX_LIST_ENTRIES],
            "roles": sorted(e["roles"])[:MAX_LIST_ENTRIES],
        })
    total = sum(e["n_executions"] for e in census)
    threshold = max(100, total // 20)
    candidates = [e["user"] for e in census
                  if e["n_executions_by_class"].get("human", 0) >= threshold
                  and "@" not in e["user"]]
    return census, candidates


# ----- row normalization -> identity rows ------------------------------------------

def _load_rows(path):
    doc = json.loads(Path(path).read_text())
    rows = doc.get("rows") if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        _die(f"{path}: expected a JSON array of rows or {{\"rows\": [...]}}")
    return [{str(k).lower(): v for k, v in r.items()} for r in rows if isinstance(r, dict)]


def _ident(fingerprint, r, n_executions, sample, first_seen, last_seen,
           is_dbt=False, fingerprint_version=None):
    return {
        "fingerprint": fingerprint,
        "fingerprint_version": fingerprint_version,
        "user": str(r.get("user_name") or ""),
        "role": str(r.get("role_name") or ""),
        "warehouse": str(r.get("warehouse_name") or ""),
        "query_tag": str(r.get("query_tag") or ""),
        "is_dbt": is_dbt,
        "n_executions": n_executions,
        "sample_text": (sample or "")[:MAX_SAMPLE_CHARS],
        "first_seen": first_seen,
        "last_seen": last_seen,
    }


def identities_from_aggregated(rows):
    """Warehouse-canonicalized rows: one row per (fingerprint x identity x is_dbt)."""
    out = []
    for r in rows:
        if not r.get("fingerprint"):
            continue
        out.append(_ident(str(r["fingerprint"]), r, int(r.get("n_executions") or 0),
                          r.get("sample_text"), str(r.get("first_seen") or ""),
                          str(r.get("last_seen") or ""),
                          is_dbt=bool(r.get("is_dbt")),
                          fingerprint_version=r.get("fingerprint_version")))
    return out


def identities_from_raw(rows):
    """Raw per-query rows (platforms without a native hash): the client
    canonicalizer assigns the fingerprint, the dbt flag is computed per ROW (not
    per sample — determinism), then group by (fingerprint x identity x is_dbt)."""
    by_key = {}
    for r in rows:
        text = r.get("query_text")
        if not text:
            continue
        fp = _client_fingerprint(text)
        is_dbt = bool(dbt_markers(text))
        key = (fp, str(r.get("user_name") or ""), str(r.get("role_name") or ""),
               str(r.get("warehouse_name") or ""), str(r.get("query_tag") or ""),
               is_dbt)
        ts = str(r.get("start_time") or "")
        c = by_key.get(key)
        if c is None:
            by_key[key] = c = _ident(fp, r, 0, text, ts, ts, is_dbt=is_dbt)
        c["n_executions"] += 1
        if ts:
            c["first_seen"] = min(filter(None, [c["first_seen"], ts]))
            c["last_seen"] = max(c["last_seen"], ts)
    return [by_key[k] for k in sorted(by_key, key=str)]


# ----- clustering ------------------------------------------------------------------

def merge_and_classify(ident_rows, fingerprint_source, opts):
    """Merge identity rows into clusters, classifying each identity separately so
    mixed traffic doesn't suppress or inflate a shape: BI and human executions are
    counted apart (admission tests each on its own — see build_findings), ETL/dbt
    executions are dropped from the counts and disclosed in evidence.
    Classification sees the COMPLETE identity sets; output lists are truncated
    only at serialization time."""
    by_fp = {}
    for i in ident_rows:
        by_fp.setdefault(i["fingerprint"], []).append(i)

    pools = {"bi_service": 0, "ad_hoc": 0, "excluded": 0}
    clusters = []
    for fp in sorted(by_fp):
        idents = sorted(by_fp[fp], key=lambda i: (-i["n_executions"], i["user"]))
        included, evidence, dropped_execs = [], [], 0
        bi_execs, human_execs, human_users = 0, 0, set()
        for ident in idents:
            klass, why = classify_identity(ident, opts)
            if klass in ("dbt", "etl"):
                dropped_execs += ident["n_executions"]
                evidence.append(f"excluded {ident['n_executions']} execution(s): {why}")
            else:
                included.append(ident)
                if klass == "bi":
                    bi_execs += ident["n_executions"]
                    evidence.append(why)
                else:
                    human_execs += ident["n_executions"]
                    if ident["user"]:
                        human_users.add(ident["user"])
        if not included:
            pools["excluded"] += 1
            continue
        pool = "bi_service" if bi_execs else "ad_hoc"
        pools[pool] += 1
        firsts = [i["first_seen"] for i in included if i["first_seen"]]
        lasts = [i["last_seen"] for i in included if i["last_seen"]]
        clusters.append({
            "fingerprint": fp,
            "fingerprint_source": fingerprint_source,
            "fingerprint_versions": sorted({i["fingerprint_version"] for i in idents
                                            if i["fingerprint_version"] is not None},
                                           key=str),
            "sample_text": included[0]["sample_text"],  # busiest kept identity
            "n_executions": bi_execs + human_execs,
            "n_executions_bi": bi_execs,
            "n_executions_human": human_execs,
            "n_executions_excluded": dropped_execs,
            "n_users": len({i["user"] for i in included if i["user"]}),
            "n_users_human": len(human_users),
            "users": sorted({i["user"] for i in included if i["user"]}),
            "roles": sorted({i["role"] for i in included if i["role"]}),
            "warehouses": sorted({i["warehouse"] for i in included if i["warehouse"]}),
            "query_tags": sorted({i["query_tag"] for i in included if i["query_tag"]}),
            "pool": pool,
            "pool_evidence": evidence,
            "first_seen": min(firsts) if firsts else "",
            "last_seen": max(lasts) if lasts else "",
        })
    return clusters, pools


def find_conflict_groups(clusters):
    """Admitted, aggregate-shaped clusters sharing an identical table set with at
    least TWO DISTINCT aggregate-signature sets (same-signature clusters aren't a
    conflict — just the same metric sliced differently). 2-8 members = a conflict
    candidate the interview adjudicates; more is a hot table (a coverage fact).
    The script deliberately does NOT judge whether two calculations target the
    same metric — that semantic call belongs to the interviewing agent and the
    analyst."""
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
        if len({tuple(m["agg_signatures"]) for m in members}) < 2:
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

def build_findings(rows, platform, scope, canonicalizer, opts,
                   scope_unavailable=()):
    ident_rows = (identities_from_aggregated(rows) if canonicalizer == "warehouse"
                  else identities_from_raw(rows))
    clusters, pools = merge_and_classify(ident_rows, canonicalizer, opts)
    census, service_account_candidates = identity_census(ident_rows, opts)
    pools.update({"system": 0, "catalog": 0, "bi_chrome": 0})

    for c in clusters:
        c["tables"] = extract_tables(c["sample_text"])
        c["agg_signatures"] = agg_signatures(c["sample_text"])
        c["conflict_group"] = None
        demoted = classify_noise(c["sample_text"], c["tables"])
        if demoted:
            pools[c["pool"]] -= 1
            c["pool"], why = demoted
            pools[c["pool"]] += 1
            c["pool_evidence"].append(why)
            c["admitted"] = False
            continue
        # Each traffic class qualifies on its own numbers: BI recurrence can't be
        # padded with human executions, and human traffic must still clear the
        # distinct-consumer bar. (bi_service skips the distinct-consumer test for
        # its BI count — one service user fronts all dashboard viewers; see
        # unavailable: viewer_counts.)
        bi_ok = c["n_executions_bi"] >= opts["min_count"]
        human_ok = (c["n_executions_human"] >= opts["min_count"]
                    and c["n_users_human"] >= opts["min_users"])
        c["admitted"] = bi_ok or human_ok

    # Conflicts over the FULL admitted set (so grouping quality doesn't depend on
    # --top), then rank admitted-first and truncate — force-keeping every member
    # of any group that made the cut, and dropping (with a count) groups whose
    # members all fell beyond it. Rejected clusters are ~90% of the bytes and
    # Stage 0 drafts from admitted ones only, so by default they stay out of the
    # file (pools{}/coverage{} still count them); --emit-rejected restores them.
    conflict_groups = find_conflict_groups(clusters)
    admitted_total = sum(1 for c in clusters if c["admitted"])
    if scope == "information_schema" and admitted_total == 0:
        # Outcome-based tripwire: an empty fallback is success-shaped (exit 0,
        # valid file) and reads as "mining done, nothing found" — when it
        # usually means the executing role can't SEE the traffic.
        _warn("0 admitted clusters from the 7-day INFORMATION_SCHEMA fallback — "
              "that usually means this role can't see the traffic, not that no "
              "dashboards run. Mining is still BLOCKED: the ACCOUNT_USAGE grant "
              "handoff applies now (privilege playbook in "
              "query-history-extraction.md).")
    clusters.sort(key=lambda c: (not c["admitted"], -c["n_executions"],
                                 c["fingerprint"]))
    emittable = (clusters if opts["emit_rejected"]
                 else [c for c in clusters if c["admitted"]])
    emitted = emittable[:opts["top"]]
    emitted_fps = {c["fingerprint"] for c in emitted}
    by_fp = {c["fingerprint"]: c for c in clusters}
    kept_groups, beyond_top = [], 0
    for g in conflict_groups:
        if any(m in emitted_fps for m in g["members"]):
            kept_groups.append(g)
            missing = [m for m in g["members"] if m not in emitted_fps]
            emitted.extend(by_fp[m] for m in missing)
            emitted_fps.update(missing)
        else:
            beyond_top += 1
    for c in emitted:  # truncate long identity lists only at serialization
        for key in ("users", "roles", "warehouses", "query_tags"):
            c[key] = c[key][:MAX_LIST_ENTRIES]

    unavailable = ["viewer_counts", *scope_unavailable]
    if canonicalizer == "client":
        unavailable.append("query_parameterized_hash")

    findings = {
        "source": "query_history",
        "platform": platform,
        "scope": scope,
        "window_days": opts["days"],
        "thresholds": {"min_count": opts["min_count"], "min_users": opts["min_users"]},
        "clusters": emitted,
        "conflict_groups": kept_groups,
        "pools": pools,
        "identity_census": census,
        "service_account_candidates": service_account_candidates,
        "unavailable": unavailable,
        "coverage": {
            "rows_in": len(rows),
            "clusters_total": len(clusters) + pools["excluded"],
            "clusters_admitted": admitted_total,
            "clusters_emitted": len(emitted),
            "conflict_groups": len(kept_groups),
            "conflict_groups_beyond_top": beyond_top,
        },
    }
    if opts["days_requested"] != opts["days"]:
        findings["window_days_requested"] = opts["days_requested"]
    return findings


def _positive_int(s):
    v = int(s)
    if v < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return v


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
    ap.add_argument("--days", type=_positive_int, default=90,
                    help="lookback window (default 90; scopes may cap it)")
    ap.add_argument("--limit", type=_positive_int, default=5000,
                    help="in-warehouse row cap for --emit-sql (default 5000)")
    ap.add_argument("--bi-users", default="", help="CSV of known BI service users")
    ap.add_argument("--bi-roles", default="", help="CSV of known BI roles")
    ap.add_argument("--bi-warehouses", default="", help="CSV of known BI warehouses")
    ap.add_argument("--exclude-users", default="",
                    help="CSV of users to exclude (ETL/orchestration)")
    ap.add_argument("--min-count", type=_positive_int, default=5,
                    help="min executions for a traffic class to admit a cluster "
                         "(default 5)")
    ap.add_argument("--min-users", type=_positive_int, default=2,
                    help="min distinct HUMAN users for the human traffic class "
                         "(default 2; not applied to BI executions — one service "
                         "user fronts all viewers)")
    ap.add_argument("--top", type=_positive_int, default=500,
                    help="max clusters emitted (default 500; conflict-group "
                         "members of emitted groups are always kept)")
    ap.add_argument("--emit-rejected", action="store_true",
                    help="also emit non-admitted clusters (demoted/below-"
                         "threshold), for debugging; by default only admitted "
                         "clusters and their conflict-group members are written")
    ap.add_argument("-o", "--out", help="write JSON here instead of stdout")
    args = ap.parse_args(argv)

    scope_entry, scope = _resolve_platform(args.platform, args.scope)
    max_days = scope_entry.get("max_days")
    effective_days = min(args.days, max_days) if max_days else args.days
    if effective_days != args.days:
        _warn(f"scope '{scope}' caps the window at {max_days} days "
              f"(requested {args.days}); findings will report the effective window.")

    if args.emit_sql:
        print(scope_entry["emit_sql"](effective_days, args.limit))
        return 0

    opts = {
        "days": effective_days, "days_requested": args.days,
        "min_count": args.min_count, "min_users": args.min_users, "top": args.top,
        "emit_rejected": args.emit_rejected,
        "bi_users": _csv(args.bi_users), "bi_roles": _csv(args.bi_roles),
        "bi_warehouses": _csv(args.bi_warehouses),
        "exclude_users": _csv(args.exclude_users),
    }
    findings = build_findings(_load_rows(args.rows), args.platform, scope,
                              scope_entry["canonicalizer"], opts,
                              scope_entry.get("unavailable", ()))

    text = json.dumps(findings, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
