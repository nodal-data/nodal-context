# AUTHORING.md

Read [GOVERNANCE.md](GOVERNANCE.md) for protected merge approval, live stale-state
checks, explicit branch testing and legacy conversion. New definitions omit
authored approval status; interview confirmation is evidence for review.


Rules for agents **editing** this repo (adding or correcting context). For rules on
**answering data questions** from this repo, see `CLAUDE.md`. Authored context is
Markdown and YAML; encrypted answer keys and support tooling have separate roles.

## Do Not
- **No statistics in context.** Qualitative business logic only. Not "~37% of
  sessions" — that belongs in the warehouse.
- **No schema duplication.** Column types live in dbt/Snowflake.
- **No invented definitions.** Leave `_To be confirmed by [owner]._` and
  proposed working-branch content rather than guessing. Wrong context is worse than missing context.
- **SQL only as query patterns.** `reference.md` "Common query patterns" may carry
  a few fenced `sql` blocks, only where the exact query form is the hard-won
  knowledge — pattern, not paste: real model/column names, `<placeholders>` for
  parameter values, each led by a `Without this: …` line naming the failure it
  prevents, analyst-confirmed, never mined from query logs. Complete runnable
  queries stay out of context. Capture approved SQL with `scripts/verified.py
  capture`: plaintext stays ignored under `evals/verified/`; only `.sql.age` or
  `.sql.sops` ciphertext is eligible for commit. Neither is answering context.

## Conventions
- YAML entities/metrics carry a `lineage:` pointer; approval lives in the authority.
- Each metric lives in `domains/<domain>/metrics/<name>.yaml`; the legacy wrapper
  and ACF 0.2 are unsupported. Definitions require protected human-reviewed merge;
  simulation cannot supply approval. Retain prior attribution in `review_history`.
- `reference.md` is written for retrieval by an agent (routing triggers, grain,
  gotchas), not as narrative — narrative goes in `context.md`.
- Add `# REVIEW: [question]` where domain-owner verification is needed.

## Metrics and methods in 0.3

Keep reusable domain-local lineage, filters and parameters in `metrics/_shared.yaml`.
Review the expanded constraints for every consumer; shared edits can invalidate
several definitions. Reference-only arithmetic declares `lineage: inherit`;
`metric(domain.name)` composes across domains. Confirm allowed dimensions and
each row/group/entity filter stage. Division requires `ratio.zero_denominator`
(YAML `null`, `zero` or `error`) and a reason. Runtime dates/windows are parameters.

Record competing definitions with `family` and distinguish their aliases. Use
`open_decisions` with explicit blocked targets for unresolved questions. Effective
readiness follows dependencies: a stored-confirmed metric may still be blocked.
Do not force SQL into the expression grammar. Use `expression_blocked_by` and
`deterministic_form` pointing to a confirmed `reference.md#pattern-<slug>` or
`methods/<slug>` when the calculation needs a reviewed pattern or method.

Root methods declare an owning domain, metrics, parameters, decisions with
`without_this` rationales, output disclosures and qualitative checks. Their bodies
contain `When to use` and `Procedure`, citing decision IDs. They carry no runnable
SQL/Python. Confirm filter overrides, stock/flow alignment and constants explicitly.
Static notebook import drafts a method; it never executes cells or confirms rules.
Each parameter needs a note, and each optional output column needs a decision
explaining when it appears. Runtime dates and undeclared computational literals
are invalid in both decisions and procedure steps; illustrative worked examples
and citations are allowed. Untyped code fences do not make executable code prose.
Entity-anchor references create real dependencies: a draft entity blocks its
method and downstream seeds. Declare referenced metrics in the method's `metrics`
list; a link alone cannot silently expand the composed metric set.

Every confirmed disambiguation emits a seed or reviewed equivalent variant.
Positive metric/method seeds require matching IR; negative-kind seeds describe
appropriate declines, not merely rejected alternatives. Evergreen time tokens
must be declared in config; absolute windows need a pinned snapshot expectation.
See `SPEC.md` and `schemas/` for the exact field contracts.

## Continuing this repo (resume or teammate handoff)

Context is built one domain at a time; picking it back up is the normal case.

- **Same machine, later.** Re-run the installed `context-interview` skill from
  your normal Claude, Codex, Cursor, or other supported agent. It searches nearby
  directories for this repo and asks before touching anything;
  if it doesn't find it, give it the path (or this repo's GitHub URL). It reads
  `context.config.yaml`, sees what's already captured, and resumes from the open
  proposed working-branch content items — it never starts over.
- **A teammate picking it up.** Install Nodal through the same native-plugin or
  skills.sh channel your team uses, invoke `context-interview`, and answer
  "continuing" with this repo's GitHub URL — the
  skill clones it and resumes. (A nearby existing clone works too; the skill finds
  those itself.) Authored context and support tooling travel with the clone;
  keys, local queues, execution traces and source notebooks do not. Configured
  encrypted answer keys travel, but require customer keys to use.
- **Do I need the dbt repo locally?** Not to answer questions, validate, or run
  evals — CI uses the git URL recorded in `context.config.yaml`. Clone it locally
  (and run `dbt parse`) only when drafting a **new** domain, so the interview can
  seed real drafts from your models; the skill will tell you the exact clone URL.
- **Running the inject eval locally.** No warehouse needed:

  ```bash
  pip install anthropic pyyaml jsonschema
  export ANTHROPIC_API_KEY=...
  python -m eval_harness.run --adapter acf --domains "<domain>"
  ```

  Inject mode skips numeric snapshot checks without actual execution evidence;
  shape and method obligations are reported separately. The confirmed baseline
  excludes draft/blocked definitions. Approved encrypted SQL travels with a clone
  and can be checked explicitly with `scripts/regress.py` and a trusted customer
  read-only executor. Install `sqlglot` for its write/multi-statement preflight.
  Keys, warehouse authentication and historical snapshots remain customer-owned.
  No executor/key/history means skipped, never passed. See
  `eval_harness/INTERFACE.md` for the protocol and `verified-regression.yml` for
  the protected, manually triggered workflow. No SQL or result artifacts are
  published by that workflow; only sanitized seed statuses reach the summary.

## Reviewing observed questions

Keep local question observations in ignored `evals/observed/queue.jsonl` and
invoke the interview's Stage 6 to review them. `scripts/review_observed.py list`
prioritizes ambiguous and frequent questions. Matching an explicitly supplied IR
with `scripts/match_question.py --domain DOMAIN --ir .nodal/reviewed-ir.json`
does not call a model or execute a query.

`review_observed.py prepare` creates a private proposal with full destination
contents and a digest. After reviewing that exact interpretation, use `apply`
with the proposal, digest and actual reviewer name. Use `resume` with the same
arguments after an interruption. New definitions/seeds and changed definitions
remain draft; confirming them is a separate interview step. Equivalent variants
preserve the seed's approval, and overflow remains in `.nodal/observed/history/`.
Concurrent edits stop application rather than being overwritten. Queue writers
must share `.nodal/observed/review.lock`, or be paused during application.
Proposals and history are local; never commit their raw question data.

## Verify notebook methods

After Stage 6 import and human method review, return directly to Stage 5 without
restarting the interview. If execution is deferred, retain the source, question,
known bindings and remaining prerequisites under `.nodal/notebook-candidates/`.
Do not invent a numerical expectation for a pending case.

Use the installed interview skill's Stage 5 notebook-verification flow after
reviewing the imported method and its dependencies. `scripts/verify_notebook.py`
orchestrates customer-selected reference, answer and judge executors. Rerun the
source in a fresh kernel and have an independent AI derive and execute its method
answer against identical pinned inputs. The answering session must not receive
notebook code, stored outputs or seed expectations. Compare keyed rows, tolerances,
required disclosures and method checks; saved outputs or matching totals alone
do not verify a method.

A run `pass` awaits human review before creating a confirmed snapshot. Record the
real approver and source revision in `verification_source`; missing dependencies,
executors or stable inputs are blocked/skipped, not passes. Python-only methods
need no SQL sidecar. Executed notebooks and receipts remain in ignored local
evidence. The source notebook stays in its original repo. Use `--help` for the
executor CLI and `eval_harness/INTERFACE.md` for its protocol.

## Review drift and validate changes

`python3 .ci/validate.py` checks schema, references, expressions and effective
readiness. Supply manifests for column validation; without them lineage is
unchecked. `.ci/coverage.py` reports definition, slicing and verification gaps
separately. Optional `.ci/semantic_lint.py` sends selected authored context to the
customer's model provider and returns unconfirmed warnings, never approvals.
It skips without a key; deterministic validation remains independent.

`.ci/drift.py` reports dependency impact. The trusted workflow publishes stale
blocks to the independent authority before any repair proposal. Review affected
definitions, rerun applicable behavior/source checks and merge the repair. Clear
only the named block for that exact reviewed revision through the protected
approval workflow. Re-grading records verification only and cannot restore
approval. See GOVERNANCE.md for deployment and offline behavior.

The configured drift workflow proposes review PRs with an issue/patch fallback.
Local commands do not publish. Commit, push or publish only when the user requests
it, after reviewing the intended diff and excluding private execution material.
