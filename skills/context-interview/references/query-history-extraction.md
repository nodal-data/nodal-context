# Query-History Extraction (Stage 0)

When the warehouse MCP probe succeeded, mine what the company **actually runs**.
BI tools are pushdown — every dashboard tile already executes in the warehouse —
so query history is a dashboard catalog and a metric-logic census that needs no BI
admin. Recurrence after canonicalization separates institutionalized logic from
ad-hoc exploration; a daily-refreshed tile is 365 history rows collapsing to one
cluster with count 365. But mined clusters are a **draft to react to**, never
truth (LLM-bootstrapped definitions from query logs measure net-negative — the
value is in the *questions* mining surfaces, not the answers). Everything you
write from findings is `status: draft`, tagged
`# query-history-derived (<fingerprint>)`, and stays excluded from the perfect
eval baseline until the analyst confirms it. **Tag, don't trust.**

**Ambiguity is the payload.** When mining finds three different revenue
calculations over the same table (run 120 / 45 / 8 times, by different teams),
that conflict *is* the interview question. The analyst's resolution is
simultaneously a context entry (a metric `expression:`) and a labeled eval seed
(with `ir:`).

## Step 1 — produce `.query-findings.json` (two phases; you run the SQL, not the script)

The miner (`scripts/query_history_extract.py`) never touches the warehouse. It
emits the extraction SQL; **you** execute it read-only via the warehouse MCP —
the same probe-first discipline as the rest of Stage 0. If the Stage-0 probe
failed (auth pending), put mining on the deferred-checks list and continue; never
block the interview on it.

**Phase A — emit, execute, save:**
```
python3 scripts/query_history_extract.py --emit-sql --platform snowflake [--days 90]
```
Run the printed SQL via the warehouse MCP (read-only SELECT — it already is).
Save the result rows **verbatim** as JSON to `.query-history-rows.json` at the
**target context repo** root (gitignored; raw SQL text lives only here).

**Phase B — cluster into findings:**
```
python3 scripts/query_history_extract.py --rows .query-history-rows.json \
    --platform snowflake -o .query-findings.json
```
Useful knobs: `--bi-users/--bi-roles/--bi-warehouses` (the analyst knows their BI
service accounts — ask: *"Which service users do your dashboards run as?"*),
`--exclude-users` (ETL accounts), `--min-count/--min-users` (admission
thresholds), `--top`, `--emit-rejected` (debug only: also write non-admitted
clusters; by default the file carries admitted clusters and their conflict-group
members, everything else stays counted in `pools{}`/`coverage{}`). Both artifacts
are transient bootstrap files, gitignored — discard after Stage 0.

**Privilege playbook (Snowflake):**
- Default scope reads `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` (365-day window,
  ~45min–3h lag — fine for mining). The MCP user cannot see it by default. On
  *"Object does not exist or not authorized"*, offer the analyst the one-time,
  least-privilege grant (an `ACCOUNTADMIN` runs it; `<USER>` = the MCP user,
  `<WAREHOUSE>` = the warehouse it queries on):

  ```sql
  USE ROLE ACCOUNTADMIN;
  CREATE ROLE IF NOT EXISTS QUERY_HISTORY_READER;
  -- ACCOUNT_USAGE views (QUERY_HISTORY among them) via the built-in governance role
  GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE QUERY_HISTORY_READER;
  GRANT USAGE ON WAREHOUSE <WAREHOUSE> TO ROLE QUERY_HISTORY_READER;
  GRANT ROLE QUERY_HISTORY_READER TO USER <USER>;
  ```

  If they can't grant it right now, re-emit with `--scope information_schema` —
  a 7-day, no-privilege fallback whose visibility is limited to what the current
  role can see. Tell the analyst you're mining a one-week, privilege-limited
  sample, and note the grant as deferred so a later session can re-mine the full
  window.
- Not on Snowflake yet? The script names the platform's history source and exits
  loudly (databricks / bigquery / redshift / fabric are registered but not
  implemented). Tell the analyst mining is unavailable on their platform for
  now and continue — dbt extraction and the interview cover the same ground by
  hand.

## Step 2 — census first, then read the findings, then draft (one domain at a time, as always)

**Census first.** The findings carry an `identity_census` (per user: traffic
classes, executions, shape count, warehouses, roles) and
`service_account_candidates` — high-volume identities that defaulted to "human"
because no pattern matched (an embedded-analytics app, a scheduler, a reverse-ETL
tool). A misclassified service account is the single biggest signal killer: one
service user can never clear `--min-users`, so its whole pool dies silently.
Before drafting anything, ask the analyst about each candidate — *"what runs as
`ANALYTICS_APP`?"* — then re-run Phase B with `--bi-users` (dashboards/apps) or
`--exclude-users` (automation) and read the new findings instead. Dogfooding
found the account's biggest identity (12.5k executions) hidden this way.

`.query-findings.json` shape: `clusters[]` (`fingerprint`, `sample_text`,
`n_executions`, `n_executions_bi`, `n_executions_human`,
`n_executions_excluded`, `n_users`, `n_users_human`, `users[]`, `roles[]`,
`warehouses[]`, `query_tags[]`, `pool`, `pool_evidence[]`, `tables[]`,
`agg_signatures[]`, `admitted`, `conflict_group`), `conflict_groups[]`,
`pools{}`, `identity_census[]`, `service_account_candidates[]`,
`unavailable[]`, `coverage{}`, `window_days` (the *effective* window —
`window_days_requested` appears when a scope capped it). Only `admitted`
clusters are draft candidates — and only they are written (plus force-kept
conflict-group members) unless `--emit-rejected`. The `bi_service` pool is
high-trust (institutionalized logic), the `ad_hoc` pool is a demand signal, not
a definition source. Three pools are content-demoted noise, counted but never
admitted and never draft material: `system` (console/session chrome — Snowsight
runs on whatever warehouse the session holds, so this traffic otherwise
masquerades as BI), `catalog` (INFORMATION_SCHEMA polling by tools), and
`bi_chrome` (row-count wrappers and filter-population scaffolding from BI/app
UIs). Traffic is counted per executing identity and per class:
BI and human executions each qualify a cluster on their own numbers (one BI
run padded by a few human runs is NOT a dashboard pattern), and ETL/dbt
executions are subtracted into `n_executions_excluded` and disclosed in
`pool_evidence` rather than suppressing the cluster.

Map each artifact to its ACF target — all `status: draft`, all tagged:

| findings artifact | ACF target (actual field) | Notes |
|---|---|---|
| admitted `bi_service` clusters | Stage-2 domain/dashboard catalog candidates, beside dbt `exposures[]` | a recurring cluster ≈ one dashboard-shaped unit: a recurring question + the tables it reads |
| cluster `tables[]` | `domain.yaml.tables.{canonical,others}` candidates; cross-check `context.config.yaml` lineage models | regex-extracted **hints** — confirm, never trust |
| `conflict_groups[]` | the interview disambiguation question → confirmed `metrics.yaml` `expression:` + an eval seed with `ir:` | the headline win; phrase it as a question (below) |
| recurring predicates in `sample_text` | hygiene-filter / `expression.mandatory_filters` candidates (`reference.md`, metric) | e.g. every cluster on a table filters `< 45 days` — ask why |
| admitted `ad_hoc` clusters | long-tail demand signal → draft seeds (`provenance: generated`, `status: draft`) + glossary candidates | lower trust; never definition candidates |
| a high-count cluster the analyst calls "the query everyone gets wrong" | `reference.md` Common query pattern (pattern-not-paste) + a `sql_shape` seed | interview-flow §4 follow-up 5 |

`conflict_groups[]` is the headline win: phrase it as a question, e.g. *"I found
three different revenue calculations on `FCT_ORDERS` — `SUM(net_revenue)` run 365
times by Tableau, `SUM(gross_revenue)` run 45 times by Looker, and
`SUM(net_revenue - refunds)` run 8 times ad-hoc. Which is the governed
definition — and do the others have legitimate names of their own?"* The
resolution lands as the metric's `expression:` and a seed whose `ir:` records the
decomposition.

## Step 3 — degrade loudly (consume `unavailable[]`, `coverage{}`, `pools{}`)

- `"viewer_counts"` in `unavailable` (always, for now) → the warehouse sees one
  service user per BI tool, not the humans behind it. Dashboard names, element
  structure, and viewer stats are optional BI-API enrichment — offer to draft an
  "email your BI admin" note rather than blocking on it.
- `"window_beyond_7_days"` / `"result_limit_pre_filter"` in `unavailable` → you
  mined the 7-day INFORMATION_SCHEMA fallback (it still uses Snowflake's native
  fingerprint); say so, and expect weekly-refresh tiles to be under-counted.
- `"query_parameterized_hash"` in `unavailable` → a platform without a native
  hash, clustered by the client-side canonicalizer; fingerprints are less exact.
- `pools.excluded` high → ETL traffic (service-user patterns) plus dbt-stamped
  queries (dbt's query comment / test scaffolding in the text — dbt logic
  reaches the interview via `dbt-extraction.md`, so keeping it here would
  double-count). Nothing to do; it was filtered.
- `pools.bi_service == 0` → no BI service users matched. Ask the analyst what
  their dashboards run as and re-run Phase B with `--bi-users` — do not treat an
  empty BI pool as "no dashboards exist".
- `pools.ad_hoc` large but nothing human admitted, and
  `service_account_candidates` non-empty → that's a misclassified service
  account swallowing the human pool, not "no humans query anything". Ask, then
  re-run Phase B (census-first step above). A short window compounds this:
  `--min-users 2` is hard to clear in 7 days — prefer the 90-day default when
  `account_usage` is available.
- **Tell the analyst what you're doing:** "History gave me 14 recurring BI
  clusters and 3 conflicting revenue calculations, but no viewer counts — I'll
  ask you which dashboards matter most."

## Guardrails

- **The miner surfaces candidates and conflicts; it never writes definitions.**
  You draft, the analyst confirms — their confirmation is the only trust event.
- Every derived line: `status: draft` + `# query-history-derived (<fingerprint>)`.
- **Raw SQL stays in the gitignored transients.** The only path from mined SQL
  into a committed file is an analyst-confirmed, pattern-not-paste Common query
  pattern (`reference-doc-skeleton.md` rules). Never paste `sample_text` into
  ACF.
- **Never name the company (or a domain) after a relation** in `tables[]` — same
  rule as dbt extraction; warehouse identifiers are often codenames.
- `tables[]` and `agg_signatures[]` come from regex, not a SQL parser — treat
  them as hints and read `sample_text` yourself before asking the analyst about
  a cluster.

## Test

The miner has a stdlib test (no pytest dep):
`python3 tests/test_query_history_extract.py`.
