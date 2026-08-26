# Wiring your dbt repo to this context repo

This directory is **reference material for your dbt repo**, not for this one.
`notify-context-repo.yml` is the sender half of the drift loop: it lives in the
dbt repo and tells this context repo when the models changed.

## The loop

```
dbt repo                              context repo (this one)
--------                              -----------------------
push to main touching models/**
  └─ dbt parse (no credentials)
  └─ force-push manifest.json to      .github/workflows/context-drift.yml
     orphan branch `dbt-manifest`  ─▶   └─ clones repo@dbt-manifest
  └─ repository_dispatch                └─ .ci/drift.py diffs columns/tests
     `lineage-changed`             ─▶   └─ drift → GitHub issue + red check
```

The manifest travels via the `dbt-manifest` branch — not inside the dispatch
payload — because GitHub caps `repository_dispatch` payloads at ~64 KB and real
manifests are far larger. The branch is a single commit, force-pushed each time,
so it never grows your repo. Because it persists, the weekly cron safety net in
the context repo also finds a fresh manifest even if a dispatch is missed.

## Setup (one time)

1. Copy `notify-context-repo.yml` into the dbt repo's `.github/workflows/` and
   fill in every `EDIT` line (source id, context repo, adapter, profiles dir,
   paths — prefix paths and the manifest path with your dbt subdirectory if the
   project is nested, e.g. `dbt/models/**` and `dbt/target/manifest.json`).
2. Create a fine-grained PAT for the dispatch:
   - Resource owner: your GitHub org
   - Repository access: **only** the context repo
   - Permissions: **Contents: Read and write** (required by the
     `POST /repos/{owner}/{repo}/dispatches` endpoint)
   Save it in the **dbt repo** as the Actions secret `CONTEXT_DISPATCH_TOKEN`.
3. In this context repo's `context.config.yaml`, point the source at the branch:

   ```yaml
   lineage_sources:
     - id: <source_id>              # must match SOURCE_ID in the sender
       type: dbt
       repo: github.com/<org>/<dbt-repo>
       ref: dbt-manifest
       manifest_path: manifest.json
   ```

4. Run the sender once by hand (Actions → notify-context-repo → Run workflow)
   to create the `dbt-manifest` branch, then establish the baseline here:

   ```
   python .ci/drift.py --update-baseline --manifest <source_id>=<path/to/manifest.json>
   ```

   and commit `.ci/lineage-baseline.json`.

If the dbt repo is **private**, also set `DBT_REPO_TOKEN` in this context repo
(fine-grained PAT, Contents: Read on the dbt repo) so the clone fallback can
fetch the branch; public repos need no token.

There is no need to gate the sender on "did the manifest really change?" — the
paths filter is the gate, `drift.py` exits clean on a no-op, and the drift issue
dedupes, so a spurious dispatch costs one green run.
