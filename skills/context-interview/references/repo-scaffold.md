# Repo Scaffold

How Stage 0 lays the repo down and wires drift detection. Mechanical, do it once
per project.

## Lay down the files

1. **Run the scaffold script** from the cloned tool repo — do not copy files by hand:

   ```
   python3 scripts/scaffold.py <target-dir>
   ```

   (default target `../analytics-context/` — a sibling of the cloned tool repo, so
   the tool repo is never authored into). The script is the single source of truth
   for the file list. It copies two layers and then self-checks:

   - **The template** (the authorable content): empty `company/`, a
     `_domain-template/`, `entities/`, `evals/seeds/`, `AGENTS.md`, `CLAUDE.md`
     (consumption-first — how an agent answers questions from this repo),
     `AUTHORING.md` (how to edit it), `README.md` (the end-user getting-started
     doc), `.claude/skills/data-question/` (the bundled "answer a question from
     this context" skill), and `context.config.yaml`.
   - **The CI support set**, so validation, drift, and the eval delta run on PRs
     from day one: `.github/workflows/`, `.ci/` (the workflow scripts —
     `validate.py`, `drift.py`, `collect_manifests.py`, `suggest.py`,
     `changed_domains.py`), `schemas/` (the ACF JSON Schemas — `.ci/validate.py`
     validates the repo's YAML against them locally, with no network),
     `scripts/dbt_extract.py` (which `drift.py` imports), and **`eval_harness/`**
     — vendored because `eval-delta.yml` runs `python -m eval_harness.run` from
     the context repo root and there is no pip package to install it from.

   **Hard gate: do not proceed to Stage 1 until the script's self-check passes**
   (`python3 scripts/scaffold.py --check <target-dir>` exits 0). A repo that skips
   part of the support set ships broken CI — this is exactly how a missing
   `schemas/` or `eval_harness/` turns into red workflows on the customer's first PR.

2. Once a dbt manifest is available, establish the drift baseline once and commit it:
   `python .ci/drift.py --update-baseline --manifest <source_id>=<path>` writes
   `.ci/lineage-baseline.json` (the snapshot drift compares against). The scaffold
   script never overwrites an existing baseline.
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

**`repo:` is the durable CI identity — never a local path.** The analyst points you
at a *local* dbt clone for extraction (Stage 0); that path is session state and must
never be written to `context.config.yaml` — the drift workflow clones `repo:` in CI,
and a filesystem path (`local:…`, `/Users/…`) can never work there. Don't ask the
analyst for the GitHub path either — derive it: run
`git -C <local-dbt-path> remote get-url origin`, normalize to `github.com/org/repo`,
and confirm in one line ("I'll record `github.com/acme/acme-dbt` as the source CI
clones for drift — right?"). Record the branch they actually build from as `ref:`.
If the clone has **no remote** (a local-only project), **omit `repo:` entirely** and
flag it — `collect_manifests.py` then reports the source as unchecked instead of
failing on an uncloneable path — and re-raise it at wrap-up when the context repo
goes to GitHub (see `SKILL.md`). `.ci/validate.py` warns on local-looking `repo:`
values on every PR as a backstop.

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

To refresh an existing repo's CI support set (workflows, `.ci/`, `schemas/`,
`scripts/dbt_extract.py`, `eval_harness/`) — e.g. after the tool repo ships fixes,
or to repair a repo scaffolded before the support set existed — run:

```
python3 scripts/scaffold.py --upgrade <target-dir>
```

Upgrade mode never touches authored content (`company/`, `domains/`, `entities/`,
`evals/`, `context.config.yaml`) and never overwrites `.ci/lineage-baseline.json`.
