# Repo Scaffold

How Stage 0 lays the repo down and wires drift detection. Mechanical, do it once
per project.

## Lay down the files

1. Copy `template/` to the target dir (default `./analytics-context/`). The
   template ships empty `company/`, a `_domain-template/`, `entities/`,
   `evals/seeds/`, `AGENTS.md`, `CLAUDE.md`, and `context.config.yaml`.
2. Copy `.github/workflows/` into the target repo so validation, drift, and the
   eval delta run on PRs from day one.
3. For each domain discovered in Stage 2, copy `_domain-template/` to
   `domains/<domain>/` and fill it in.

## Wire `context.config.yaml` (do not defer this)

This is the file that keeps "context separate from lineage" safe. As you discover
each domain's tables (Stage 2, Q4), record the lineage pointer:

```yaml
version: 0.1
warehouse: snowflake
lineage_sources:
  - id: dbt_core
    type: dbt                       # dbt | sqlmesh | raw_sql | none
    repo: github.com/acme/acme-dbt
    ref: main
    manifest_path: target/manifest.json
domains:
  <domain>:
    lineage:
      - source: dbt_core
        models: [<model_a>, <model_b>]
```

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

## Updating an existing repo

If `context.config.yaml` already exists, do not overwrite. Read it, find which
domains are already captured, and resume — ask the analyst which domain to work on
rather than starting over. Append new seeds; never rewrite confirmed ones without
asking.
