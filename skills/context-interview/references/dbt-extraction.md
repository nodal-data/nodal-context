# dbt Extraction (Stage 0)

When a dbt project is available, seed the draft from it instead of hand-eliciting
everything. dbt encodes grain, value sets, join paths, and dashboards as structured
artifacts — but they are a **draft to react to**, never truth. Everything you write
from dbt is `status: draft`, tagged `# dbt-derived (<source node>)`, and stays
excluded from the perfect eval baseline until the analyst confirms it. A wrong dbt
description is exactly the plausible-but-wrong failure mode; **tag, don't trust.**

## Step 1 — produce `dbt-findings.json`

The extractor (`scripts/dbt_extract.py`) reads dbt and writes a compact summary you
draft from. It does **not** write ACF — you do, through the confirm loop.

**Primary — manifest (run `dbt parse` first; no warehouse needed):**
```
# in the dbt project (cheap, offline; `dbt compile` instead if you also want SQL):
dbt parse
# then, from this repo:
python3 scripts/dbt_extract.py --manifest <dbt_project>/target/manifest.json -o .dbt-findings.json
```

**Fallback — bare clone, can't run dbt:**
```
python3 scripts/dbt_extract.py --source <dbt_project> -o .dbt-findings.json
```
The fallback reads source `.yml` (descriptions + tests) and scrapes `ref()` from
model `.sql` for the dependency graph. It does **not** parse Jinja SQL for filters
(too fragile) and yields no `relation` names — prefer `dbt parse` whenever possible.

Write `.dbt-findings.json` to the **target context repo** root; it's gitignored
there (a transient bootstrap artifact, not ACF). Discard it after Stage 0.

## Step 2 — read the findings, then draft (one domain at a time, as always)

`dbt-findings.json` shape: `models[]` (`name`, `relation`, `description`,
`columns[]`, `depends_on[]`, `tests[]`, `grain_hint[]`), `exposures[]`,
`unavailable[]`, `coverage{}`.

Map each artifact to its ACF field — all `status: draft`, all tagged:

| dbt artifact (in findings) | ACF target (actual field) | Notes |
|---|---|---|
| model `description` | `domain.yaml.summary` (+ `context.md` stub) | field is **`summary`**, not `description` |
| model `relation` | `domain.yaml.tables.{canonical,others}` | real warehouse table names |
| column `description` | entity `mappings` / `analytical_notes` | texture the DB schema lacks |
| test `accepted_values` (`kwargs.values`) | entity `mappings` (value enumeration) | high-value, low-ambiguity |
| `grain_hint` (from `unique` / `unique_combination_of_columns`) | `domain.yaml.grain` + `reference.md` — **confirm with the analyst** | grain is the #1 wrong-answer mode |
| test `relationships` (`kwargs.to`/`field`) | entity `important` (join hint) | canonical join path |
| test `not_null` | `known-issues.md` caveat stub | "nulls forbidden here — investigate" |
| `exposures[]` | `domain.yaml.dashboards[]` + domain clustering | the Stage-2/Stage-5 dashboard backlog |
| `depends_on[]` graph | `context.config.yaml` lineage models + domain boundaries | which models feed an exposure = domain shape |
| compiled SQL (when `compiled_sql: true`) | `metrics.common_filters` / hygiene-filter candidates in `reference.md` | best-effort; only when `dbt compile` ran |
| dbt semantic models / metrics | `metrics.yaml` stubs only | draft only, never auto-confirm |

`grain_hint` is the headline win: phrase it as a question, e.g. *"dbt has a
uniqueness test on `soap_note_id` for `fct_session_financials` — is one row really
one SOAP note, or is the real grain note × service?"*

## Step 3 — degrade loudly (consume `unavailable[]` and `coverage{}`)

dbt projects vary wildly (some, for instance, has **no** exposures,
accepted_values, or relationships, and 0 documented columns). Do not fake what isn't
there — fall back to the interview:

- `"exposures"` in `unavailable` → there is no dashboard catalog in dbt; ask the
  Stage-2 question ("list the dashboards your team maintains and who owns each").
- `"accepted_values"` / `"relationships"` in `unavailable` → elicit value sets and
  join paths by hand in Stage 3.
- low `coverage.with_description` / `with_column_descriptions` → don't draft
  narrative from nothing; ask.
- **Tell the analyst what you're doing:** "dbt gave me grain evidence and table
  names but no value lists or dashboards, so I'll ask you for those directly."

## Guardrails

- **Never name the company (or a domain) after a database/schema/relation.** Those
  are warehouse identifiers — often codenames. Use
  `relation` only to fill `domain.yaml.tables`; the company and domain *names* come
  from the analyst in Stages 1–2, not from what you queried. If unsure, ask.
- Every dbt-derived line: `status: draft` + `# dbt-derived (<node id>)`.
- Descriptions and semantic-layer metric defs are **often stale/aspirational** —
  confirm hard before flipping to `confirmed`.
- The script drafts nothing into ACF; you draft, the analyst confirms. Same
  draft-vs-confirmed discipline as `repo-scaffold.md`.

## Test

The extractor has a stdlib test (no pytest dep): `python3 tests/test_dbt_extract.py`.
