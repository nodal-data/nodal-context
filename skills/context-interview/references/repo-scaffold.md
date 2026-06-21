# Repo Scaffold

How Stage 0 lays the repo down and wires drift detection. Mechanical, do it once
per project.

## Lay down the files

1. Copy `template/` to the target dir (default `./analytics-context/`). The
   template ships empty `company/`, a `_domain-template/`, `entities/`,
   `evals/seeds/`, `AGENTS.md`, `CLAUDE.md` (consumption-first — how an agent
   answers questions from this repo), `AUTHORING.md` (how to edit it), `README.md`
   (the end-user getting-started doc), `.claude/skills/data-question/` (the bundled
   "answer a question from this context" skill), and `context.config.yaml`.
2. Copy `.github/workflows/` into the target repo so validation, drift, and the
   eval delta run on PRs from day one.
3. For each domain discovered in Stage 2, copy `_domain-template/` to
   `domains/<domain>/` and fill it in.
4. Replace the `[company]` placeholder in `README.md` and `CLAUDE.md` with the
   company name (from the analyst or their website — never from a schema).
5. **Initialize the repo.** Run `git init` in the target dir and make an initial
   commit once the scaffold is in place (`git add -A && git commit -m "Initial
   analytics context scaffold"`). This is safe, offline, and reversible, and makes
   the "review by PR" workflow real from the first domain. Do *not* create or push a
   GitHub remote here — that's the wrap-up offer in `SKILL.md`.

## Wire `context.config.yaml` (do not defer this)

This is the file that keeps "context separate from lineage" safe.

**One cheap question up front (breadth-first):** before recording any source, ask
*"Which data platforms do your dashboards run on — just Snowflake, or a mix (e.g.
Snowflake + BigQuery + Postgres)?"* Capture only the *list*, not full source details.
If it's one platform, set the top-level `warehouse:` and leave every source without a
`warehouse:` — done. If it's several, set the top-level `warehouse:` to the most
common one (the default) and plan to tag the others' sources with `warehouse:` lazily,
as each domain that uses them is reached. Don't enumerate every source now.

Then, as you discover each domain's tables (Stage 2, Q4), record the lineage pointer:

```yaml
version: 0.1
warehouse: snowflake                # default platform; per-source `warehouse:` overrides it
lineage_sources:
  - id: dbt_core
    type: dbt                       # dbt | sqlmesh | raw_sql | none
    repo: github.com/acme/acme-dbt  # no `warehouse:` → inherits the default
    ref: main
    manifest_path: target/manifest.json
  # add a per-source `warehouse:` only when that source is on a non-default platform:
  # - id: dbt_bq_marketing
  #   type: dbt
  #   warehouse: bigquery
  #   repo: github.com/acme/marketing-dbt
  #   ref: main
  #   manifest_path: target/manifest.json
domains:
  <domain>:
    lineage:
      - source: dbt_core
        models: [<model_a>, <model_b>]
```

A domain's platform is **derived** from the sources its `lineage:` references — there
is no per-domain warehouse field. A domain whose models span two platforms simply
lists one lineage entry per source (the array already supports this); don't invent a
federated marker.

If there is no dbt project, set `type: none` and list the raw table names — drift
detection degrades to "warehouse column-set changed" instead of "model changed,"
which is still useful. The point is that **every domain has a lineage pointer even
when context lives in its own repo.** A domain with no pointer cannot be protected
from drift, so flag it.

## Draft-vs-confirmed discipline

- Auto-extracted stubs are written `status: draft`.
- A definition becomes `status: confirmed` only after the analyst says so.
- The validation workflow warns (does not fail) on `draft` so they're visible in
  the PR; the eval workflow excludes `draft` from the perfect baseline.

### dbt draft

When a dbt project is present it's the richest draft source — prefer it over raw
schema. Run `scripts/dbt_extract.py` and draft from its findings per
`references/dbt-extraction.md`. Two rules on top of the discipline above:

- Every dbt-derived stub also carries a `# dbt-derived (<node id>)` tag, so its
  origin is auditable in the PR.
- The extractor reports an `unavailable` list (what dbt didn't provide — e.g. no
  exposures, no `accepted_values`); elicit those by hand in the relevant stage rather
  than leaving silent gaps.

## Updating an existing repo

If `context.config.yaml` already exists, do not overwrite. Read it, find which
domains are already captured, and resume — ask the analyst which domain to work on
rather than starting over. Append new seeds; never rewrite confirmed ones without
asking.
