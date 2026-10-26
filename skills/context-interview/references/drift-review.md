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

## Prepare and inspect status changes

After the report identifies a real source change, prepare a patch:

```bash
python3 .ci/drift.py --manifest core=/path/to/manifest.json \
  --prepare-patch --json-out .nodal/drift-impact.json
```

Exit 1 indicates drift and can accompany a successfully prepared patch. Exit 2
is a setup/validation failure. `--fail-on-unchecked` uses exit 3 for incomplete
source coverage when no drift was otherwise found. Preparation writes only
ignored local plan/history files. It changes confirmed affected objects to draft
in the proposed patch, including named query patterns. It preserves comments,
method prose and earlier human approval metadata as historical attribution.
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
Application is a local status change, not a commit, PR, push or publication.

For authored context changes, supply `--changed-files ... --base-root /path/to/base`
instead of manifest arguments. Base and head graphs preserve impact from removed
or renamed objects. An unresolved graph conservatively selects all domains but
cannot produce a precise status patch. Fix the graph or provide a valid base.
PR evaluation routing uses Git object snapshots containing context data only,
never executing code from the base revision.

## Automated review publication

The trusted default-branch `context-drift` workflow collects configured dbt
manifests, prepares the same status-only patch, and opens or updates one draft PR
per source-change batch. Its branch is `nodal/context-drift-<batch>`. The PR lists
affected objects, source changes and the batched Stage 5 snapshot review. This is
an unmerged proposal: default-branch status and the lineage baseline do not change.

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

Previously approved shape/entity seeds are eligible for automatic restoration
only after a fresh passing re-grade, unchanged authored interpretation, and
confirmed/unblocked dependencies. A passing grade alone is insufficient. Do not
manually flip seeds to confirmed just because an upstream metric was reviewed.
Missing judge/execution capability leaves evidence incomplete. Automated check
timestamps and results belong in ignored run output, never in `approver` or
`confirmed_at`.

Run fresh checks with the customer's BYO model key using:

```bash
python3 scripts/regrade_seeds.py --seed seed:orders.seed.yaml
python3 scripts/regrade_seeds.py --seed seed:orders.seed.yaml --restore
```

The first command reports only; `--restore` performs a fresh check and persists
eligible seed status changes in that same invocation. It cannot apply a saved
verdict. The original question and every stored variant must pass. Generation
receives governed definitions/prose, not seed expectations or verified SQL; the
separate judge receives the obligations. Draft query patterns are excluded from
answer context. Entity checks include the resolved entity definition. Method
checks requiring actual execution remain incomplete when only generated SQL is
available; model claims about results do not supply execution evidence.

Approval evidence comes from the most recent stored human-confirmed seed at the
same path in Git history, starting at `HEAD` (override with `--approved-ref`).
History scanning is bounded to 100 path changes and never executes historical
code. A shallow/missing approval history, renamed seed, changed interpretation,
changed attribution, lost dimension or unresolved reference requires review.
The search cannot bypass a newer differing confirmation to find an older match.
Only stored status may change; original human approval fields and comments remain.

All checks are bound to the source/config/schema/baseline fingerprints. Concurrent
edits reject restoration. A partially interrupted multi-seed restoration retains
its private evidence; rerun to check the remaining draft seeds afresh. An
incomplete drift application must finish before restoration. Evidence and check
timestamps live under ignored `.nodal/regrades/`; public output is seed IDs,
statuses and sanitized categories. Exit 1 means a failed grade, 3 means missing
checks or pending dependency review, and 2 means invalid/changed context.

The trusted drift workflow runs these checks when `ANTHROPIC_API_KEY` is present.
During drift it checks the proposed draft graph, so a passing seed still reports
“re-grade passed; dependency review pending” while its definitions need review.
After lineage has been reconciled and dependencies confirmed, subsequent scheduled
or manual runs can propose eligible seed restorations on a
`nodal/seed-regrade-<batch>` review branch. No model key means an explicit skip.
The workflow summary reports failures/skips even when no restoration is proposed;
it uploads no generated answers, expected values or judge transcripts. Model
re-grading sends the governed context and obligations to the customer's model
provider; it is not warehouse execution or human approval.

Once the source changes and context have been reviewed, explicitly refresh the
baseline with `--update-baseline` and all required manifests. Missing sources or
models prevent baseline replacement. Commits, pushes and publication still require
the user's instruction.
