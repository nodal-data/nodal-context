# Reviewing affected context

Drift reports are review input. Neither validation nor coverage mutates authored
status. A lineage report identifies changed or missing upstream models, affected
objects and dependency paths, unchecked sources, and snapshot seeds to verify in
one Stage 5 session. Missing manifests mean unchecked lineage, not a clean check.

For a customer context repo, run the local drift checker with the manifests that
the customer has acquired through its existing read-only workflow:

```bash
python3 .ci/drift.py --manifest core=/path/to/manifest.json --out .nodal/drift-report.md
```

The checker uses per-metric, method, entity, pattern and seed dependencies, including
cross-domain consumers. A shared entity with unknown scope causes conservative
review. A negative or unresolved seed can need review when new definitions make
its question answerable. It must not retain a stale refusal merely because it has
no metric IR.

## Prepare and inspect review changes

After the report identifies a real source change, prepare a patch:

```bash
python3 .ci/drift.py --manifest core=/path/to/manifest.json \
  --prepare-patch --json-out .nodal/drift-impact.json
```

Exit 1 indicates drift and can accompany a successfully prepared patch. Exit 2
is a setup/validation failure. `--fail-on-unchecked` uses exit 3 for incomplete
source coverage when no drift was otherwise found. Preparation writes only
ignored local plan/history files. For legacy objects that already have authored
status fields or explicit pattern markers, it can propose a legacy status patch.
Status-free definitions and unmarked patterns remain status-free; do not add
approval fields to them. Live authority records stale blocks independently of
any proposed patch. Preparation preserves comments, method prose and earlier
human approval metadata as historical attribution.
It does not rewrite a business definition, remove a dimension, or refresh the
lineage baseline.

Read the generated `status.patch` and `plan.json`. Explain which upstream change
caused each affected definition/seed and what needs review. Explicit application
uses the exact plan path and digest returned by preparation:

```bash
python3 .ci/drift.py --apply-plan .nodal/drift/RUN_ID/plan.json --sha256 REVIEWED_DIGEST
```

An already-authorized status update need not ask for redundant approval. The
separate apply command makes the write explicit and reviewable. Source/schema
changes after preparation reject application. Interrupted writes can be resumed
with the same command; conflicting edits are preserved. A completed application
is idempotent. Do not delete a pending journal to force conflicting changes.
Application is a local legacy patch, not approval, clearance, a commit or publication.

For authored context changes, supply `--changed-files ... --base-root /path/to/base`
instead of manifest arguments. Base and head graphs preserve impact from removed
or renamed objects. An unresolved graph conservatively selects all domains but
cannot produce a precise status patch. Fix the graph or provide a valid base.
PR evaluation routing uses Git object snapshots containing context data only,
never executing code from the base revision.

## Automated review publication

The trusted default-branch `context-drift` workflow collects configured dbt
manifests, records stale blocks in the authority ledger, prepares any applicable
legacy patch, and opens or updates one draft PR
per source-change batch. Its branch is `nodal/context-drift-<batch>`. The PR lists
affected objects, source changes and the batched Stage 5 snapshot review. This is
an unmerged proposal: authored definitions and the lineage baseline do not change.
Live authority blocks take effect before the repair proposal is merged; a patch
is not required to revoke eligibility.

`.ci/collect_manifests.py` emits a JSON map consumed by `--manifest-map`; it does
not emit shell arguments. Dispatch manifests must belong to configured dbt
sources. Clone acquisition reads only a regular Git blob, without checking out
or executing upstream source code. Customer-provided runner authentication is
not persisted in the clone or printed. Acquisition failures leave the source
unchecked, with no reuse of an older downloaded manifest as current evidence.

`.ci/prepare_drift_publication.py --base-ref <default-branch>` checks the plan
digest, context, schema and baseline revisions and requires context matching the
checked-out commit. It writes a local publication payload and review artifact;
it does not publish anything itself. The workflow's GitHub step checks the remote
default-branch revision again and never force-updates a branch. An existing
proposal with human edits or a closed PR is left intact for review.

When policy or permissions prevent PR creation, the workflow opens or updates a
batch-specific issue with the unapplied patch and affected list. Long reports
link the complete review artifact rather than claiming the abbreviated preview
is complete. If issues are disabled too, publication fails and the workflow
artifact remains available for 30 days. Only `affected.md` and `status.patch` are
uploaded; private plans, manifests and execution evidence are excluded. The
workflow remains failing while drift or unchecked sources remain unresolved.

Enabling this workflow authorizes that repository's CI publication path. Running
the local report/prepare commands does not publish, commit or push anything.

## Review and verify the batch

Review each affected definition with its human owner. Re-confirming a metric
does not re-confirm methods or seeds. Preserve original attribution; do not
replace it with an automation or simulator identity. Methods, changed meanings,
removed dimensions and negative seeds need human review. Collect the listed
snapshot seeds into one Stage 5 session, using dashboard or independent notebook
verification as appropriate.

Re-grading records independent behavior evidence; it never restores definition
approval or clears stale blocks. Run:

```bash
ACF_BRANCH_TEST=1 python3 scripts/regrade_seeds.py --seed seed:orders.seed.yaml
```

This explicitly tests proposed context and cannot approve it. `--restore` is
rejected. The original question and variants must pass; missing judge or execution
capability remains incomplete. Generated answers never receive seed expectations.
Keep private evidence under `.nodal/regrades/` and report sanitized outcomes.

The trusted drift workflow records stale targets in the independent authority
before opening a repair proposal. No authored status patch is the stale-state
source. Review the definitions, refresh the lineage baseline with complete
manifests, merge through protected human review, and run fresh applicable checks.
Use the protected context-approval workflow to clear the named block for the
exact reviewed revision. It verifies successful check runs after the block.
An unrelated merge, passing model grade or changed status field cannot clear it.
See GOVERNANCE.md and the canonical SPEC for authority setup and expiry behavior.
Commits, pushes and publication still require the user's instruction.
