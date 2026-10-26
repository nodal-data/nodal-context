# Developing and checking the ACF 0.3 migration

The canonical contract is [SPEC.md](../SPEC.md). ACF 0.3 immediately retires the
legacy single-file metric layout and ACF 0.2 runtime support. The one-time
`scripts/split_metrics.py` converter reads legacy YAML only as migration input.
It is not a dual-layout reader. Review definitions, approval metadata and config
before upgrading a converted repo.

Support-file upgrades produce a private `.nodal/migrations/scaffold-<hash>.md`
report comparing preserved authoring files with incoming fresh templates. Review
ignore rules, agent instructions and configuration changes there; do not apply
template stubs over customer definitions. The report is not a historical template
diff because no prior template baseline is stored. Repeating an unchanged review
reuses its content-addressed report. Keep `.nodal/` ignored.

Conversion preserves per-metric review comments even when values move into shared
fragments, and retains a byte-exact legacy backup. It rejects malformed YAML and
case-fold destination collisions before writing. Output publication cannot replace
a concurrently created file; rollback preserves concurrent edits to files already
published. An equal existing destination remains untouched. Empty legacy domains
become an empty metrics directory and can be converted again as a no-op.

## Local dependencies

Use a project virtual environment. Core validation requires `jsonschema` and
`pyyaml`. The converter adds `ruamel.yaml`. Static notebook import adds `nbformat`
and `sqlglot`. The optional reference notebook executor adds `nbclient` and
`ipykernel`, plus the notebook owner's existing data dependencies. No command
automatically installs dependencies or changes host Jupyter configuration.

The direct package test suite needs the static/conversion dependencies:

```bash
python3 -m pip install jsonschema pyyaml ruamel.yaml nbformat sqlglot
python3 scripts/sync_skill_payload.py --write
python3 scripts/sync_skill_payload.py --check
python3 scripts/run_tests.py
python3 scripts/lint_skills.py
python3 .ci/validate.py
```

Run the repository's Claude/Codex package validators and isolated installed-skill
scaffold smoke tests before calling a release complete; see `AGENTS.md` and
`.github/workflows/tool-ci.yml`. Offline unit checks do not establish live agent,
warehouse or dashboard acceptance. No package publication is part of a local
check.

## Notebook development loop

Statically import a draft into an existing, valid context repo:

```bash
python3 scripts/import_notebook.py /path/to/analysis.ipynb \
  --root /path/to/context --name cohort-retention --domain customers \
  --repo <source-repository> --source-path retention/analysis.ipynb --ref <actual-revision>
```

The method is written to `methods/<name>.md`; a local review report is written
under `.nodal/imports/`. Existing files are never replaced. No notebook cell is
executed and no stored results are copied into context. Omitting `--ref` records
the notebook content hash rather than inventing a source commit.

Review candidate parameters, metric references, output schema, business decisions
and every missing `without_this` rationale with the analyst. An exact aggregation
candidate still needs review; a near-match is possible definition drift.

For actual verification, follow the
[notebook verification reference](../skills/context-interview/references/notebook-verification.md).
It documents the case JSON, explicit reference/answer/judge executors, independent
agent context, evidence contract and separate human-confirmation command.
Execution is opt-in and customer-controlled. Missing evidence is skipped/blocked;
no model claim substitutes for executed rows.

After confirmation, `.ci/coverage.py --notebook-run
'<seed>.seed.yaml=.nodal/notebook-runs/<run>/comparison.json'` can explicitly check
the local receipt, context fingerprint and source bytes. Changed evidence is
stale; unavailable evidence is reported separately. This is a freshness check,
not a rerun, and never changes the historical expectation. Without the option,
coverage reports a historical snapshot with source revision unchecked.

The synthetic fresh-kernel check uses a real notebook kernel and deterministic
test answer/judge executors, without a warehouse or AI API:

```bash
python3 -m pip install nbclient ipykernel
python3 tests/test_notebooks.py --kernel
```

This supplements the offline direct suite. It checks kernel execution and
comparison plumbing; it is not a live AI-method fidelity result. Task sandboxes
that prohibit local kernel sockets need an approved environment for this check.

For actual AI fidelity on fictional inputs, explicitly run:

```bash
python3 -m pip install anthropic nbclient ipykernel
python3 tests/test_notebooks.py --live-ai
```

This uses the operator's existing `ANTHROPIC_API_KEY` and the harness client model.
It makes separate answer and judge calls, reruns a synthetic notebook in a fresh
kernel, and executes the generated SQL against an in-memory SQLite input snapshot.
The answer model receives method definitions, parameters and table schema, with
no notebook code, reference outputs or expected values. A restrictive SQLite
authorizer blocks writes, external databases and non-allowlisted functions;
generated Python is never executed. This fixture executor is not a customer
warehouse adapter. The printed temporary directory retains execution receipts,
the comparison and model diagnostics for review. A successful run does not create
a confirmed seed or assert human approval. The normal direct suite checks the
fixture executor offline and makes no model calls.

## Artifact boundaries

Run outputs, source notebooks, credentials, briefs, migration backups and local
planning specs remain outside package payloads. `/specs/` is ignored in the tool
repo; canonical root `SPEC.md` remains tracked. On case-insensitive filesystems,
`spec.md` and `SPEC.md` are the same file. Generated payload files are refreshed
only with `sync_skill_payload.py`, never edited separately.

## Verified SQL and regression checks

The [verified SQL reference](../skills/context-interview/references/verified-sql.md)
documents local capture/encryption, ignore migration, recipient rotation and the
explicit customer executor protocol. `scripts/verified.py` uses external
[age](https://github.com/FiloSottile/age) and
[SOPS](https://getsops.io/docs/) executables; it implements no cryptography.

Direct tests cover atomic writes, path rejection, honest crypto/execution failures,
read-only SQL preflight, temporary cleanup, sanitized CI output and real synthetic
SQLite query execution. For real backend round trips, provision `age`, `age-keygen`
and `sops` into a temporary tools directory, then run:

```bash
python3 tests/test_verified.py --crypto-dir /path/to/temporary-tools
```

This test generates disposable synthetic keys inside its temporary directory;
it never reads customer identity contents. The migration has been checked with
age 1.3.2 and SOPS 3.13.3. Local package code never generates customer keys.
The protected workflow still needs customer runner provisioning and a real
historical-snapshot adapter before live acceptance can be claimed.

## Simulated analyst checks

The [tracked clean-room harness](../scripts/integration/README.md#quick-simulated-analyst-loop)
supports the current-worktree quick path, `--auto` compatibility, explicit marker
handoff and resume, including a pause before scaffolding. The default direct
suite runs `tests/test_simulation.py` with synthetic files and a fake host, proving
the file/protocol boundaries without starting an AI agent or reading customer
briefs. `scripts/simulated_analyst.py` manages local state and human attestations;
it never reads the brief or acts as the responder.

Maintainers can opt into a real short interview with
`tests/test_simulation.py --live claude` or `--live codex`. Normal host permissions
apply. Live acceptance is separate from offline tests and cannot be claimed from
fake-host output. Unknown answers pause non-interactive runs with exit code 3.

Each actual simulation launch writes a private `simulation-summary.json` beside
the room's projects, even when paused before scaffolding. It lists the generated
context, draft metrics/methods, transcript, pending questions, open decisions and
verification follow-ups. Draft validation is separate from execution verification.
Static notebook import can contribute drafts without requiring a live notebook
or dashboard check; unresolved human review and execution stay pending.

## Drift and routing checks

`acf_runtime/impact.py` traces per-object lineage, definition and blocker impact.
`.ci/changed_domains.py` uses data-only Git snapshots of both sides of a PR;
deleted/renamed objects retain their consumers through the union graph. Invalid
graphs select all available domains with a diagnostic. Shared entities without
explicit consumer scope are deliberately conservative.

`.ci/drift.py --prepare-patch` produces a local status-only preview and
`--apply-plan ... --sha256 ...` explicitly applies/resumes it. Comments, method
prose, historical human approval fields and the lineage baseline are preserved.
The [drift review reference](../skills/context-interview/references/drift-review.md)
documents the review and Stage 5 batch. Tests use disposable Git histories,
filesystem crash injection and tampered/stale proposals; no remote branches or
PRs are created by these checks.

The trusted default-branch drift workflow now prepares a checked publication
payload and opens/updates one draft PR per source-change batch. It uses non-forced
branch updates and preserves conflicting human edits. Policy/API failures fall
back to a batch-specific issue and a narrowly scoped patch/list artifact. Missing
issue capability fails publication while retaining the artifact. Local reporting
and preparation still perform no remote writes.

`tests/test_drift_publication.py` verifies revision-checked payloads using local
disposable Git repositories and calls a Node test with injected GitHub API
responses. It covers idempotent PR reuse, unrelated base updates, branch races,
human edits, closed batches, permissions, issue reuse, and long-report artifacts.
These tests do not establish live GitHub policy acceptance. Manifest acquisition
tests use local Git blobs and mocked failures, with no real credentials/network.

`scripts/regrade_seeds.py` now checks original questions and variants against fresh
independent answers, retrieves the latest stored human approval from Git data,
and gates optional `--restore` on unchanged interpretation and ready dependencies.
The trusted workflow checks its proposed draft graph and can later propose seed
restorations after lineage/dependency clearance. Missing keys, failed/incomplete
grades and unavailable method execution leave seeds stale. Private evidence is
fingerprinted under `.nodal/regrades/`; public summaries omit code/expectations.

`tests/test_regrade.py` uses injected generation/judgment, disposable Git approval
history and concurrent source changes. Publication tests exercise both pending
drift checks and clean-graph restoration proposals. They prove the gating and
data boundaries, not real model accuracy. No live model checks are implied.
Draft patterns are now omitted from both compiled and injected reference context;
explicit draft compilation visibly labels them. Fenced-code headings and status
strings do not alter actual pattern section boundaries or status.

## Optional semantic warnings

Run `python3 .ci/semantic_lint.py` in a customer context repository. With a BYO
`ANTHROPIC_API_KEY`, it compares reference/metric routing, method prose/declarations
and context/reference narrative. Without a key it reports a skip and never imports
the model SDK. `--format json` produces structured output; the default Markdown
report is under ignored `.nodal/semantic-lint/report.md`. All unavailable/error
outcomes are nonblocking. The ordinary `.ci/validate.py` remains authoritative
for deterministic failures and never invokes the model.

Inputs are bounded to 32,000 UTF-8 bytes per complete comparison, with at most 20
new requests per invocation. Oversized/excess inputs are reported as skipped.
Warnings must cite matching quotes from both inputs; the quotes do not prove the
model's interpretation. Only derived warnings are cached, keyed by content,
model, prompt/lint version and output schema. There is no decryption, notebook
access, query execution, observation ingestion or seed-answer prompt input.

`semantic-context.yml` is a separate optional job. For PRs to the default branch
it runs trusted base-revision tooling and schemas, fetching the proposed revision
as Git data without checking out or executing its code. It posts unconfirmed
warnings as a PR comment and retains only the derived report for 14 days. Local
`--revision <sha>` uses the same data-only snapshot path. Model request/response
failures and publication failures cannot block schema validation.

`tests/test_semantic_lint.py` injects a model function and tests the input allowlist,
key gate, bounded requests, quoted citations, invalid/cache/model outputs, content
and model/version invalidation, symlinks, escaped Markdown, private sidecar
exclusion and non-execution of untrusted revision code. No live model or PR
publication is performed by these tests.

## Complete worked example

[Example Orchard](../examples/example-acf-03-company/README.md) is the complete
synthetic 0.3 graph: five revenue siblings with shared fragments, renewal components
and a deterministic successor-link pattern, canonical customers and alternative
cohort anchors, explicit review blockers, variants, negative/entity/shape seeds,
a synthetic partial-follow-up snapshot, and a deliberately unverified draft
notebook snapshot. Fictional approvers demonstrate the format only. No customer
notebook or external source identifier is presented as real evidence.

`tests/test_acf_example.py` validates the graph with an inline synthetic manifest,
tests family ambiguity/default and selector matching, and computes a finite toy
cohort to check fixed membership, distinct identity, test exclusions, partial
windows and empty-denominator nulls. Grader tests use an explicitly synthetic
semantic judge and do not establish live AI or warehouse correctness. Ordinary
example validation without a manifest honestly reports unchecked column lineage.

## Column and method dependency checks

The YAML loader rejects non-string mapping keys before schema validation.
Diagnostics for shared fragments include both their metric reference and shared
definition locations; JSON exposes these as `related` path/field entries and the
CLI prints them. Expansion keeps this source mapping outside authored definitions.

Method constraints and explicit overrides are checked against inherited filters
on every arithmetic component, preserving branch populations. A method cannot
bypass a base filter through an intermediate metric with no direct filter list,
or treat agreement with one component as agreement with all of them.

`acf_runtime/columns.py` derives matching aliases from complete manifest lineage.
Bare columns, model-qualified columns and manifest-ID-qualified columns normalize
only when ownership is unambiguous. Missing models/manifests provide no alias proof;
known ambiguous spellings remain unresolved. Requested and allowed dimensions,
including inherited metric and method dimensions, use the same evidence. This
metadata never rewrites authored definitions. A single selected method branch uses
that metric's evidence rather than ambiguity from unselected alternatives.

`tests/test_column_matching.py` covers complete/incomplete lineage, repeated model
pointers, duplicate model names, cross-source ambiguity, nested filters, inherited
and method dimensions, and branch selection. `tests/test_methods.py` covers entity
anchor/whole-file dependencies, draft cascades and lineage impact through method
seeds, wrong-kind references, parameter notes/usage, optional-column decisions,
code fences and procedural constants/dates. These are deterministic checks;
semantic lint still handles qualitative disagreements that syntax cannot prove.
