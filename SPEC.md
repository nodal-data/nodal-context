# Analytics Context Format (ACF) — v0.1

The on-disk format the interview produces and the harness reads. It is plain
Markdown + YAML in a git repo, so the review surface is a pull request and the
change-trigger is a GitHub Action.

ACF deliberately separates **three audiences**:

| File kind | Written for | Optimized for |
|---|---|---|
| `context.md`, `overview.md`, `terminology.md` | humans | onboarding, narrative, "why" |
| `reference.md` | the agent at query time | retrieval: routing triggers, gotchas, grain |
| `*.yaml` (entities, metrics, domain) | both + CI | machine-validatable structured facts |

This split is the main upgrade over a single narrative doc. The `reference.md` is
the file the agent actually reads to answer a question, and it is written for an
LLM, not a person — explicit `IF … DO NOT …` routing, grain, exclusions, and
wrong-answer modes, with no prose it has to wade through.

## Design rules (these are load-bearing)

1. **A human owns every definition.** The model may draft; a person confirms. Any
   field marked `status: draft` is excluded from the "perfect" eval baseline until
   confirmed.
2. **No statistics in context.** Notes are qualitative business logic ("exclude
   BHPN — different reimbursement cycle"), never "~37% of sessions." Numbers go
   stale; business logic doesn't. 
3. **Context is separate from lineage, but never *unlinked* from it.** Every
   domain, entity, and metric carries a `lineage:` pointer (repo + path + ref) so
   drift detection can fire when the upstream model changes. Separation is for
   enterprises with many pipelines; the pointer is what keeps separation safe.
4. **Every confirmed disambiguation emits an eval seed.** The interview writes
   `evals/seeds/*.yaml` as a byproduct. These are the ground truth the delta is
   measured against.
5. **Everything is CI-checkable.** Each YAML kind has a JSON Schema in `schemas/`.
   A PR that breaks the schema fails review.

## Directory contract

```
<your-context-repo>/
├── context.config.yaml          # repo metadata + domain↔lineage source map
├── AGENTS.md                    # machine orientation (how an agent should navigate)
├── CLAUDE.md                    # authoring rules for agents editing this repo
├── company/
│   ├── overview.md              # business model, what the company does
│   ├── terminology.md           # cross-domain glossary
│   └── org-structure.md         # domain ownership
├── domains/<domain>/
│   ├── domain.yaml              # structured metadata: tables, grain, lineage ptr
│   ├── context.md               # narrative business context (humans)
│   ├── reference.md             # retrieval doc (the agent reads THIS) ← key file
│   ├── metrics.yaml             # metric defs: formula, params, caveats
│   ├── entities.yaml            # domain-specific entity values (optional)
│   └── known-issues.md          # data-quality gotchas
├── entities/<group>.yaml        # cross-domain entities (payers, clients, geo…)
└── evals/
    └── seeds/<name>.seed.yaml   # interview-harvested ground-truth pairs
```

Placement rule:
**cross-domain entity** (lives in a `dim_*` table or spans fact tables) →
`entities/`; **domain-specific status/type** (one fact table, one owner) →
`domains/<domain>/entities.yaml`.

## Where a domain comes from

A domain in ACF maps to **how the company already thinks about a slice of the
business — usually a cluster of dashboards.** The interview discovers domains by
asking which dashboards exist and who owns them, then treats each coherent cluster
as a domain. This is why `domain.yaml` carries a `dashboards:` list: a dashboard
cluster is the unit of "a line of business or function," and it's also the richest
source of eval seeds (the questions those dashboards answer are real questions).

## File: `context.config.yaml` (the drift seam)

The one file that makes "context lives apart from lineage" safe. It maps each
domain to its upstream lineage source(s), so a change there can flag stale context.
See [`template/context.config.yaml`](./template/context.config.yaml).

**Multiple warehouses / clouds.** The top-level `warehouse:` is the repo-wide
*default*. Each `lineage_sources` entry may carry its own `warehouse:` (snowflake |
bigquery | …) when a company's domains span platforms; an entry without one inherits
the default. A source's effective platform is `source.warehouse ?? top-level
warehouse`. There is **no per-domain warehouse field** — a domain's platform is
derived from whichever sources its `lineage:` references. A single domain whose
models live on two platforms simply lists one lineage entry per source (the array
already supports this); don't invent a federated marker. Drift detection must resolve
each source's platform by this rule and diff against that source's manifest/connection.

```yaml
version: 0.1
warehouse: snowflake            # default platform; per-source `warehouse:` overrides it
lineage_sources:
  - id: dbt_snowflake
    type: dbt                   # no `warehouse:` → inherits the default (snowflake)
    repo: github.com/acme/acme-dbt
    ref: main
    manifest_path: target/manifest.json
  - id: dbt_bq_marketing
    type: dbt
    warehouse: bigquery         # this source lives on BigQuery
    repo: github.com/acme/marketing-dbt
    ref: main
    manifest_path: target/manifest.json
domains:
  session-financials:
    lineage:
      - source: dbt_snowflake
        models: [fct_session_financials, dim_client, dim_provider]
    # drift fires when any listed model's column set or test set changes
  marketing-attribution:        # platform derived from the source → BigQuery
    lineage:
      - source: dbt_bq_marketing
        models: [fct_touchpoints]
```

## YAML kinds (full field lists in `schemas/`)

### entity (`entities/*.yaml`, `domains/*/entities.yaml`)
`name`, `description`, `mappings` (column→value meaning), `analytical_notes`,
`important` (disambiguation), `lineage`, `status` (draft|confirmed).

### metric (`domains/*/metrics.yaml`)
`name`, `definition` (prose, human-owned), `grain`, `parameters` (what the user
must specify), `caveats`, `common_filters`, `lineage`, `status`.

### domain (`domains/*/domain.yaml`)
`name`, `summary`, `tables`, `grain`, `dashboards`, `owner`, `lineage`.

### eval seed (`evals/seeds/*.seed.yaml`)
`question`, `intent` (the disambiguated meaning), `expected` (one of:
`semantic_entity` | `sql_shape` | `value_at_snapshot`), `provenance`
(`interview` | `dashboard` | `correction`), `domain`, `status`. See
[`SPEC` of seeds](./schemas/evalseed.schema.json) and
[harvesting reference](./skills/context-interview/references/eval-seed-harvesting.md).

## Versioning

ACF is versioned at the repo root (`context.config.yaml: version`). The harness
declares which ACF versions it supports. Breaking changes bump the minor while
v0.x, the major after 1.0.

## Relationship to other formats

ACF is **one** input to the measurement harness, not a prerequisite. The harness
also reads Kaelio `ktx` (`semantic-layer/*.yaml` + `wiki/*.md`), dbt
(`manifest.json` + `schema.yml` docs), and raw markdown. See
[`eval-harness/INTERFACE.md`](./eval-harness/INTERFACE.md) for the normalized
intermediate representation all of these map into.
