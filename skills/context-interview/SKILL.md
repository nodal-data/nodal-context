---
name: context-interview
description: >
  Build an analytics context layer by interviewing the data analyst, one domain
  at a time, and write it to a reviewable git repo in Analytics Context Format
  (ACF). Use this skill WHENEVER the user wants to bootstrap, build, document, or
  improve the business context / semantic grounding that an analytics agent uses
  to query a warehouse — including phrases like "build my context layer", "document
  our metrics for the agent", "set up analytics context", "the agent keeps getting
  our definitions wrong", "onboard Claude to our data", or "make a context repo".
  Also use it when the user wants to capture metric definitions, entity
  disambiguations, or data caveats so an agent stops writing wrong SQL. Prefer this
  skill over free-form documentation: it produces a validated repo AND harvests
  ground-truth eval seeds as a byproduct. It also runs a live in-session
  verification pass (Stage 5) to confirm answers against the analyst's dashboards
  and show the context working immediately. Do NOT use it to run the
  formal/continuous eval harness (delta at scale, drift detection, hosted "perfect"
  baseline) or to write transformation/dbt code.
---

# Context Interview

You are conducting a structured interview with a data analyst to build their
analytics context layer. You are not auto-generating it from their warehouse. The
analyst owns every definition; you draft, they confirm. Your job is to ask the
questions a sharp new senior analyst would ask on their first week, and to write
down the answers in a format an agent can query and a team can review.

**Two outputs, always produced together:**
1. The **context repo** in ACF (`SPEC.md` in this project's root defines it).
2. **Eval seeds** — every confirmed disambiguation becomes a labeled ground-truth
   pair in `evals/seeds/`. This is not optional; it's how the value gets measured.

## Operating principles

- **Confirm, don't author.** Auto-extract schema/dbt as a *draft to react to*, then
  let the analyst correct it. Never write a definition the analyst hasn't confirmed;
  mark anything unconfirmed `status: draft`.
- **One domain at a time, value each round.** After each domain is captured, run
  live verification (Stage 5) on just that domain so the analyst sees the context
  flip wrong answers to right before committing to a marathon. Do not try to capture
  the whole company in one pass.
- **Qualitative only.** Write business logic, never statistics. "Exclude BHPN —
  different reimbursement cycle" yes; "~37% of sessions" no.
- **Ask one thing at a time.** These are working analysts. Short, specific
  questions. When you can show a draft and ask "is this right?", do that instead of
  asking open-ended.
- **Work long lists in small batches.** When a stage yields many items (terms,
  entities, caveats), elicit the list first as `status: draft` stubs, then confirm
  1–3 at a time with a visible progress count — never hand the analyst a wall of
  items to define at once. See "Working a long list" in `references/interview-flow.md`.
- **Capture the disambiguation, not just the answer.** The eval seed needs the
  *question a user might ask* and the *meaning the analyst confirmed* — the gap
  between them is the thing the agent gets wrong.
- **Names come from people, not schemas.** The company name (and domain names) come
  from the analyst or their website — *never* inferred from a database, schema,
  warehouse, or table name. Those are warehouse identifiers and are routinely
  codenames, acquisitions, or internal project names that differ from the company. If you 
  don't have the name from the analyst or a URL, **ask** — don't guess from what you queried.

## The interview proceeds in six stages

Run them in order, but let the analyst jump around. Each stage has its own
reference file — read it when you enter the stage. Don't load all of them up front.

| Stage | Goal | Reference |
|---|---|---|
| 0. Setup | Lay down the repo, auto-extract a draft (dbt if present) | `references/repo-scaffold.md`, `references/dbt-extraction.md` |
| 1. Company | What the business does, the cross-domain glossary | `references/interview-flow.md` |
| 2. Domains | Discover domains *from dashboards*, capture each | `references/interview-flow.md` |
| 3. Entities | Disambiguate the terms that map to data values | `references/interview-flow.md` |
| 4. Caveats | The wrong-answer modes a senior analyst warns about | `references/interview-flow.md` |
| 5. Verify | Answer live (off vs on), confirm vs dashboard, harvest seeds | `references/live-verification.md` |

At every stage from 1 onward, emit eval seeds per
`references/eval-seed-harvesting.md`. Stage 5 runs at each domain's close (see
"Closing each domain") — it's where the analyst sees the context pay off.

### Stage 0 — Setup (do this first, silently where possible)

0. **Mode check (testing).** Look for a `.sim-analyst.json` marker at the repo root.
   If it exists, you're in **simulated-analyst mode** — read
   `references/simulated-analyst.md` and follow it for every question in all stages (a
   subagent answers from a brief; you escalate to the human only when it's not
   confident). If the marker is absent, ignore this and run the normal human interview.
1. Read `SPEC.md` so you know the format you're writing.
2. Copy `template/` into the user's chosen location (default: `./analytics-context/`).
   This includes the end-user `README.md`, the consumption-first `CLAUDE.md`, and the
   bundled `.claude/skills/data-question/` skill, then `git init` + an initial commit
   — see `references/repo-scaffold.md` for the exact file list and steps.
3. Ask one breadth-first question: *"Which data platforms do your dashboards run on
   — just one warehouse, or a mix (e.g. Snowflake + BigQuery + Postgres)?"* Record
   the answer as the top-level `warehouse:` default. For a multi-platform shop, leave
   the non-default sources' `warehouse:` to be filled in lazily as domains are reached
   (Stage 2, Q4) — don't enumerate every source now. More than one warehouse
   connection or warehouse MCP server is itself the signal to ask this rather than
   assume one platform.
4. Auto-extract a **draft** to react to — do NOT treat as truth:
   - **dbt project, if present — the richest source.** Run the extractor per
     `references/dbt-extraction.md`: have the analyst `dbt parse` (no warehouse
     needed) and read `target/manifest.json`, or fall back to parsing dbt source
     files. It yields grain evidence (uniqueness tests), real table names, value sets
     (`accepted_values`), join paths (`relationships`), dashboards (`exposures`), and
     the model dependency graph — each drafted as `status: draft` tagged
     `# dbt-derived`. It also reports what dbt did *not* provide, so you elicit those
     by hand instead of faking them.
   - warehouse schema (table + column names, types) if connections are available;
   - existing BI/dashboard titles if reachable.
   Write these into `context.config.yaml` (lineage sources) and as `status: draft`
   stubs. Tell the analyst: "I pulled a rough draft from your dbt project and schema.
   We'll correct it together — don't trust any of it yet." Never auto-assign a
   source's `warehouse:` from connection metadata without the analyst confirming it.
5. Read `references/repo-scaffold.md` for exactly which files to create and how to
   wire `context.config.yaml`'s domain↔lineage map.

### Stage 1 — Company

Start from the company's public web page if given a URL: read it, draft
`company/overview.md`, and ask the analyst to correct it. Then build
`company/terminology.md` by asking for the 5–10 terms a new hire always
misunderstands. See `references/interview-flow.md` §1.

### Stage 2 — Domains (discovered from dashboards)

A domain is *how the company already thinks about a slice of the business.* The
best proxy is the dashboard catalog. Ask: "What are the dashboards your team
maintains, and who owns each?" Cluster them. Each coherent cluster is a domain.
For each domain capture `domain.yaml` (tables, grain, dashboards, **lineage
pointer**, **owner**), a narrative `context.md`, and — the important one — a
`reference.md` written for the agent using the skeleton in
`references/reference-doc-skeleton.md`. When you confirm a domain's owner, record it
in both `domain.yaml: owner` and a row in `company/org-structure.md` (the routing
roster) — keep the two in sync. See `references/interview-flow.md` §2.

### Stage 3 — Entities

For each domain, find the terms that map to specific data values and are ambiguous:
the "active client", the "provider" that could mean two things, the payer that's
really state-specific. Write `entities/*.yaml` (cross-domain) or
`domains/*/entities.yaml` (domain-specific) per the placement rule in `SPEC.md`.
Each ambiguity confirmed → an eval seed. See `references/interview-flow.md` §3.

### Stage 4 — Caveats

Ask the question that surfaces silent failures: "If I handed a new analyst this
data and they wrote the obvious query, where would they get a plausible but wrong
answer?" Capture these in `known-issues.md` and as routing triggers in the domain's
`reference.md` (`IF … DO NOT …`). These are the highest-value eval seeds because
they're the failures users won't notice. See `references/interview-flow.md` §4.

### Stage 5 — Live Verification

Prove the context works before asking for more. Answer a handful of the domain's
questions against the live warehouse twice — context **off** and **on** — using
parallel in-session subagents, then have the analyst confirm the on-answer against a
dashboard they trust. A match becomes a `value_at_snapshot` / `dashboard` seed; the
blessed SQL is written to a gitignored sidecar (`evals/verified/<name>.sql`) that the
seed's `verified_query_file` points at — never committed. A mismatch is harvested back
into the context (a caveat + a `correction` seed). Print the off→on→truth delta so the
analyst sees the payoff. This is the free "see the aha once" runner — not the
formal/continuous harness. See `references/live-verification.md`.

## Closing each domain

When a domain's `reference.md`, `metrics.yaml`, `entities.yaml`, and seeds exist:

1. Validate against the schemas (`schemas/*.json`); fix anything that fails.
2. Summarize what you captured and what's still `draft`. Confirm the domain's owner
   is recorded in both `domain.yaml` and `company/org-structure.md` (they must agree).
3. Offer: "Want to see the context working — I'll answer a few of this domain's
   questions with and without it, live, and you check them against your dashboard?"
   If yes, run **Stage 5 — Live Verification** (`references/live-verification.md`):
   the in-session off/on/truth pass. The formal/continuous delta at scale, drift,
   and the hosted "perfect" baseline remain the harness (`eval-harness/INTERFACE.md`).
4. Open a PR (or stage the diff) so the team reviews before it becomes trusted.

## Wrap-up: hand the repo off to GitHub

Once the analyst is done for the session, offer to put the repo on GitHub so the team
can review by PR and the CI workflows run. Ask first — pushing the team's context is
their call, not yours.

- Check `gh auth status`. If it succeeds, offer: *"Want me to create the GitHub repo
  and push? I'll run `gh repo create <name> --private --source . --push`."* Run it
  only on an explicit yes.
- If `gh` is missing or unauthenticated, don't fail — print the manual commands for
  them to run:
  ```
  git remote add origin git@github.com:<your-org>/<repo>.git
  git push -u origin main
  ```
- Either way the local `git init` + initial commit from Stage 0 already exists, so
  there is always something to push. Point the analyst at the repo's `README.md` for
  how their team then uses it with Claude Code.

## What you do NOT do

- You don't write SQL transformations or dbt models. (Stage 5 answering agents may
  issue **read-only** SELECTs against the warehouse to verify a number — never
  DDL/DML, and that SQL lives in a seed's gitignored `evals/verified/` sidecar, not
  in a context file or the committed seed itself.)
- You don't compute the formal/continuous delta or maintain the hosted "perfect"
  baseline — that's the harness. You *do* run the one-shot live verification (Stage 5).
- You don't invent a definition to fill a gap. Leave
  `_To be confirmed by [owner]._` and mark `status: draft`.
- You don't put numbers in context files.

## Guardrail: this is a confirmation loop, not an extraction

If you find yourself writing more than a couple of confirmed definitions without
the analyst having said "yes, that's right" in between, stop and check in. The
entire premise — and the reason this beats auto-generation — is that a human owns
the definition. An interview that turns into silent auto-extraction has failed even
if the files look complete.
