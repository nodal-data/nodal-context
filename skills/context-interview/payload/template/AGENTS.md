# AGENTS.md

This is [company]'s business context for analytical data, in ACF 0.3. Use it to
interpret questions; warehouse metadata establishes technical structure, not
business meaning. `AUTHORING.md` governs edits and `SHARING.md` governs distribution.

## Answering a data question

1. Identify the domain and form a metric or method IR. Metrics use a canonical
   name plus dimensions, typed filters, grain and time window. Methods use a
   canonical method, resolved component metrics and bound parameters. Resolve
   alias/family ambiguity with the user before selecting a definition.
2. Always read structured definitions: `domains/<domain>/metrics/<name>.yaml`,
   optional `_shared.yaml`, root `entities/*.yaml` and domain entities. Use the
   normalized registry when available. Expand shared and transitive references;
   honor grouped mandatory filters, entity-filter stages, parameters, grain,
   allowed dimensions, ratio policy and caveats. Methods live at `methods/<slug>.md`.
3. Check effective readiness. Human approval is required for confirmed definitions;
   `status: confirmed` does not override an open decision or draft dependency.
   Draft query patterns are not governed guidance. A deterministic-form metric is
   defined by its reviewed pattern/method, not by an invented expression.
4. Follow the retrieval ladder. For an equivalent metric, add `reference.md`.
   For a new slice, decomposition or method, add `context.md` and the relevant
   method body. For unresolved/ambiguous questions, also read company overview
   and terminology before escalation. Honor routing exclusions and failure-mode
   rationales. Without matching capability, do not claim measured coverage.
5. Use `scripts/match_question.py` with reviewed IR when available. Definition,
   slicing and verification coverage are separate. Equivalent structure across
   time tokens or parameter values does not transfer snapshot verification.
   Unknown tokens, unsupported dimensions and unresolved semantics need clarification.
6. Present the interpretation and material assumptions before execution. Preserve
   existing session approval; revise the plan if a material choice changes. For
   methods, include parameter/default choices, selected metric branches, decisions,
   output disclosures and checks. Use only already-authorized read-only warehouse
   tools or customer executors. Never run DDL/DML, install notebook dependencies
   implicitly, request credentials or claim execution without actual evidence.
7. Report the actual result, implementation and caveats. Check method outputs and
   qualitative relationships against evidence, not a model assertion. Missing
   sources/execution remain explicit gaps. Notebook verification requires a fresh
   reference run and independent method answer with identical pinned inputs.

Use seed IDs/IR metadata only to locate definitions and assess structural coverage.
Do not feed seed expectations, variants, verified SQL, ciphertext or prior result
rows into answer generation. Keep evaluated seeds out of retrieval. Answer keys
and pinned snapshots belong to a separate verification step, with provenance and
revision/filter limits preserved.

## Editing context

No Nodal source checkout is required. Follow `AUTHORING.md` and use the installed
`context-interview` skill for guided creation, correction or Stage 6 demand review.

- Keep qualitative business logic in context. Statistics stay in the warehouse;
  reviewed pinned values belong only in snapshot seeds.
- Write one metric per `metrics/<name>.yaml`. ACF 0.2, `metrics.yaml` and LookML
  metric layouts are unsupported; migrate explicitly before support-file upgrades.
- Methods contain decisions and prose, not runnable code. Static notebook import
  produces drafts; it neither executes the notebook nor confirms its business rules.
- Humans own confirmations. Confirmed metrics/methods/seeds require `approver` and
  `confirmed_at`. A simulator or model cannot supply them. Preserve historical
  attribution when drift makes an artifact draft; fresh eligible seed re-grading
  may restore a previously approved seed, never confirm a metric or method.
- Every confirmed disambiguation produces a reviewed seed or equivalent variant.
  Use negative-kind seeds for appropriate declines/escalations, not merely for an
  incorrect alternative interpretation. Stage 6 review is resumable and explicit.
- Only `setup-nodal` writes `.nodal.local.json`; do not store errors or secrets there.
- Run `python3 .ci/validate.py` (requires `jsonschema pyyaml`). Optional semantic
  lint produces warnings only. Commit, push or publish only when requested; inspect
  the intended diff and exclude local observations, credentials and run evidence.

Plaintext approved SQL stays ignored under `evals/verified/`; configured age/SOPS
ciphertext travels with the repository. Neither is answering context. Never serve
`.nodal/`, queues, captures, runs or verification artifacts through generic context
retrieval. See `AUTHORING.md` for verification and drift commands.
