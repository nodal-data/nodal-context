# Approval and freshness operations

Context is proposed until its exact revision is merged into the designated
`approval_branch` (`main` by default) through enforced human review and checks.
A branch name, a local `status`, a passing test, or a copied receipt is insufficient.

## Authority setup (maintainer-operated)

1. Protect the approval branch: require at least one human review, CODEOWNER
   review, dismissal of stale reviews, strict `validate` and `approval-policy`
   checks, and all applicable behavior checks. Enforce on administrators; disable
   force pushes, deletion and review bypass. Add the context owners to CODEOWNERS.
2. Create a separate `acf-governance` branch containing `state.json`:
   `{"approval_branch":"main","events":[],"freshness":{}}`. Restrict writes to
   the governance service identity. Set `ACF_GOVERNANCE_WRITER` on consumer
   hosts and as a repository variable to that single service login or GitHub App
   slug. Enforce state-ref restrictions for administrators too. The live reader
   verifies these restrictions. Context authors and ordinary workflow tokens
   must not be able to update/delete/force-push this ref. Keep its Git history.
3. Provision the service identity through GitHub's own credential facilities.
   `ACF_GOVERNANCE_TOKEN` needs contents writes and read access to branch
   protection, PR reviews and checks. Nodal does not provision credentials.
   Restrict its use to the trusted approval and drift workflows. Protect workflow
   changes with CODEOWNERS. Both `nodal-governance` and `nodal-governance-repair`
   environments permit only the approval branch. The repair environment requires
   human review for clearance; routine merge recording needs no second approval.
   Drift revocations run promptly
   without waiting for repair approval. Set `ACF_APPROVAL_BRANCH` if not `main`.
4. On consumer hosts, install trusted tooling outside authored context. Set
   `ACF_GOVERNANCE_REPOSITORY=owner/repo` and `ACF_GOVERNANCE_COMMAND` to a JSON argv
   array with an absolute executable, for example
   `["/opt/nodal/bin/python","/opt/nodal/scripts/governance_github.py","read"]`.
   `gh` manages authentication. Never source commands from a context repository.

An absent authority, inaccessible protection settings, missing source checks,
expired checks, dirty content, or an unrecognized revision blocks governed use.
The reader also checks that the latest source workflow completed and published
its state; pending checks or failed publication block use immediately.
The reader always fetches live state; there is no offline approval fallback.
Local copies must retain their approved Git commit and exact content. Exports
carry deterministic generated files (independent of build date and checkout name)
and `governance.json` identifying the revision, content hash, approval event,
ledger head and freshness evidence. They are snapshots, not perpetual approval:
consumers must run `scripts/compile_skill.py APPROVED_SOURCE --verify-export EXPORT`
(using the original `--name` override if any) to recheck the live authority and
recompile/compare exported files before
using them as governed guidance. The skill evaluation adapter requires
`ACF_EXPORT_SOURCE` pointing to that approved checkout, or explicit branch-test
mode, for ACF exports. Plain exported text cannot enforce revocation.

## Detection and repair

`context-drift` writes an append-only block event to the authority ref before
publishing any repair proposal. It records target IDs, source evidence, revision
and reason. Dependency propagation blocks metrics, methods, patterns and seeds.
A source that cannot be checked blocks use too. Periodic source checks expire in
24 hours; live authority responses expire in five minutes. Source checks run on
each approval-branch push as well as dispatch and schedule, so a merge does not
wait for the six-hour scheduled refresh. Dispatch source
changes promptly; no system can detect changes that have not been reported.

Merge the reviewed repair, run fresh applicable behavior/source checks, then run
`context-approval` manually with the block ID, repair reason and passing checks
URL. Its protected environment requires human approval. The clearance names the
block and exact reviewed repair revision. It cannot clear a different block or
approve an older revision. A later protected merge inherits an existing clearance
only when the authority proves Git ancestry and the affected definitions,
dependencies, domain/company prose and configuration retain identical digests.
Changes to that scope require fresh review and clearance. An unrelated merge
never clears an uncleared block. Preserve every event and source record.
Repeated detection can create additional blocks; each must be addressed.

Consumers still reject missing approval/freshness evidence for the revision.
With valid authority evidence, eval and export exclude blocked definitions and
their dependents individually while retaining unrelated eligible definitions.
Unstructured prose from affected domains is withheld; domains with no eligible
definitions are omitted. Blocked seeds are excluded individually. Re-grading explicitly tests
proposed context without granting approval. CI regression workspaces preserve
the exact commit identity without copying Git credentials or plaintext SQL;
skipped execution returns a nonzero check result.

## Authoring and tests

Use a named working branch for interview, notebook and simulator output. New
objects have no authored `status`. Interview decisions and verification receipts
remain evidence; only reviewed merge grants definition approval. Query/notebook
verification is separate and may be missing, failed, or outdated even when the
definition is approved.

Use `.ci/validate.py --branch-test --require-ready` before merge. Consumers and
regression tools expose `--branch-test`; the eval adapter accepts
`branch_test=True`. `ACF_BRANCH_TEST=1` is an explicit process-wide test mode for
customer harnesses. This mode permits proposed definitions but never claims
approval or live freshness. Reports and exports identify it. Do not set it for
production answers. Dependency and structural failures remain failures.

Legacy conversion is `scripts/migrate_approval.py ROOT --admit-legacy` after the
owner authorizes admission of existing drafts. The converter retains original
fields in `review_history` and creates backups. Without that option it refuses
legacy drafts. Remove backups from the review tree before merging. The conversion
itself does not publish authority evidence. The repository owner has authorized
admission of the legacy content in this package's 0.3 migration; customer
repositories require their own explicit authorization. Existing history stays in
Git. Legacy fields accepted during conversion never grant live approval.
