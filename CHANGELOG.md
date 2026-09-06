# Changelog

## 1.5.0 — 2026-09-03

- Add opt-in isolated host-state testing with a fresh Codex home or Claude bare
  mode while preserving the existing clean-project default.
- Launch interactive Codex clean-room tests with the required `workspace-write`
  sandbox so the sibling context repository is accepted as a writable root.
- Install local or Git-ref Codex marketplace snapshots inside the isolated home
  and support authenticate-then-launch prepared rooms without copying secrets.
- Capture non-interactive transcripts and add a browser-install lifecycle
  scenario that checks configured state, restart and approval guidance, and
  suppression of repeated installation offers.
- Add a public agent onboarding guide and an isolated pre-install scenario that
  verifies one-distribution installation, consent boundaries, and the new-task
  handoff to `setup-nodal`.
- Document the separate macOS-account or VM smoke test required for faithful
  Codex Desktop, browser, approval, and restart coverage.

## 1.4.0 — 2026-09-02

- Clarify the current technical operator and domain-expert audiences, including
  enterprise adoption through verified domain-by-domain rollout.
- Separate representative evaluation from production onboarding and document
  optional automated dashboard verification before browser consent.
- Persist browser intent as ask-when-needed, manual, or automated; suppress
  repeated installation offers and distinguish a required restart from a
  missing binding.
- Clarify how Nodal's active interview, evidence, and human confirmation differ
  from passive documentation generation.
- State explicitly that the open-source package sends no data or credentials to
  Nodal, and distinguish it from the separate paid, opt-in hosted path.

## 1.3.0 — 2026-08-27

- Add read-only query-history visibility probes and document permissions,
  retention windows, degraded modes, and privacy caveats for Snowflake,
  BigQuery, and Redshift.
- Add product and context-validation diagrams covering the interview, governed
  answer, dashboard verification, and enterprise learning loops.
- Strengthen the five-question test drive and dashboard-validation handoff,
  including filter-aware captures and human-read fallback behavior.

## 1.2.0 — 2026-08-27

- Add `challenge-result` for user-requested skeptical second reviews of completed
  analytics answers.
- Add context-isolated and structured same-context challenge modes that test both
  the reported number and the user's expectation without treating either as
  ground truth.
- Add `UPHELD`, `REPLAN`, and `INCONCLUSIVE` outcomes with assumption and
  hypothesis ledgers, bounded read-only diagnostics, and escalation gates.
- Route material corrections back through `analytics-plan` so a revised plan
  receives fresh approval before any new execution.

## 1.1.0 — 2026-08-27

- Add `analytics-plan` as the single plan-before-query workflow across ACF, KTX,
  dbt, local documentation, approved documentation MCPs, and warehouse evidence.
- Add an auditable, explicitly uncalibrated uncertainty v0 with expert-escalation
  gates before and after execution.
- Add `verify-result` for plan-fidelity, grain/join, and plausibility review.
- Add `analyst-handoff` as a transition-focused orchestrator over
  `context-interview`.
- Replace generated `data-question` with the universal `analytics-plan`; generated
  context repos remain directly consumable through `AGENTS.md` and `CLAUDE.md`.
- Extend `.nodal.local.json` with classified local and MCP context sources while
  continuing to reject secrets and raw connection errors.

## 1.0.0

- Package `context-interview`, `dashboard-verify`, and explicit-only
  `setup-nodal` for Claude, Codex, and skills.sh installation.
- Add the manifest-driven, hash-checked context scaffold distribution mirror.
- Add guarded project-local configuration and consent-based browser binding setup.
- Preserve clone-and-run development and generated-repository workflows.
- Add a tracked, non-destructive clean-room integration harness while keeping
  operator briefs, connection configuration, and permissions local.

## Release checklist

- [ ] Run `python3 scripts/sync_skill_payload.py --check` and all tool CI locally.
- [ ] Install from a temporary checkout with Claude; confirm all seven namespaced
      skills and bundled hidden files/scripts are present.
- [ ] Install from a temporary checkout with Codex; list the available plugin and
      confirm all seven skills load.
- [ ] Install into a temporary project with `npx skills@latest add`; confirm
      scripts, executable modes, `.claude`, `.gitignore`, and `.gitkeep` survive.
- [ ] Invoke setup in each native host, confirm `.nodal.local.json`, and consent to
      a test `.mcp.json` merge without overwriting an existing binding.
- [ ] With authenticated read-only connections, run all three capability probes.
- [ ] Complete a `context-interview` test drive against a temporary context repo.
- [ ] Exercise `analytics-plan` against ACF, KTX, and an approved documentation
      MCP; verify an evidence conflict produces a clarification and escalation.
- [ ] Run `verify-result` against a missing mandatory filter and a fanout fixture.
- [ ] Run `challenge-result` against an upheld answer, a material time/filter
      defect that produces `REPLAN`, and a missing-evidence case that produces
      `INCONCLUSIVE`; confirm no revised SQL runs before approval.
- [ ] Complete an `analyst-handoff` domain and confirm it emits eval seeds.
- [ ] Run the tracked clean-room harness against the source checkout, installed
      Claude and Codex plugins, and a temporary skills.sh installation; complete
      its resume check and generated-repository assertions.
- [ ] Install the Codex plugin in a fresh isolated host home and run the
      `browser-install-lifecycle` scenario against both the local release
      candidate and its Git release ref.
- [ ] Run `agent-guided-onboarding` from an empty isolated Codex home, then paste
      the public agent-guide prompt into the clean Desktop smoke-test account.
- [ ] From a separate macOS user or restored VM snapshot, smoke-test Codex
      Desktop installation, project-server approval, browser launch, and the
      post-install restart path.
- [ ] Invoke `dashboard-verify` against an authenticated dashboard and reconcile
      at least one value and filter window.
- [ ] Confirm repository and isolated installed-skill scaffold smoke tests pass.
- [ ] Bump plugin semver for every published package change and add release notes.
