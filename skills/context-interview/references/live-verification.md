# Stage 5 — Live Verification

The payoff stage. You've captured a domain; now *show the analyst the context
works* before they commit to more. Answer real questions against their live
warehouse twice — once with the context off, once on — and have the analyst confirm
the on-answer against a source they already trust (a dashboard). Every confirmation
is the strongest kind of eval seed: a real number, pinned to a date, with the SQL
that produced it.

This is the free, in-session realization of the eval harness's "one-shot runner that
lets you see the aha once" (`eval_harness/INTERFACE.md`). It is **not** the
formal/continuous harness — you are not computing a hosted "perfect" baseline or
re-running on every PR. You are running a single live off/on/truth pass and
harvesting ground truth from it.

Run it per domain at domain close (the "Closing each domain" step in `SKILL.md`),
or across several domains once a few are built. Re-run it later the same way — that
is what "following evaluations" means here.

## 1. Assemble the question set

Prefer questions the analyst can read a number off a dashboard for — that's what
makes the truth cheap and trustworthy:

- the `canonical_question` of each dashboard in this domain's `domain.yaml`
  (these become `provenance: dashboard` seeds), plus
- the disambiguation/caveat seeds already harvested this session (Stages 3–4) — the
  silent-failure cases are exactly where context should flip a wrong answer to right.

A handful (≈3–6) per domain is plenty. Lead with the caveat-bearing ones.

## 2. Pre-flight

- Confirm which warehouse MCP server / database is live (the same one the domain's
  lineage points at). If none is reachable, say so and skip to harvesting seeds
  without live numbers — don't fake it.
- Re-run any warehouse checks deferred earlier in the session for connectivity
  (Stage 0's probe may have failed on auth — dataset listings, empirical grain
  checks). If the analyst reauthed since, these now resolve open questions
  cheaply — and if the Stage-0 `ACCOUNT_USAGE` grant landed, re-mine query
  history: fresh conflict groups are ready-made verification questions.
- Ask the analyst to have the relevant dashboard open: *"Have the 'Collection Rate
  by Payer' dashboard up — I'll ask you to read a number off it in a moment."*

## 3. Spawn the answering agents in parallel

For each question, spawn **two** subagents (Agent/Task tool) — batch them all in a
single message so they run concurrently; cap concurrency to a handful so you don't
hammer the warehouse, and `log` what's batched. Each subagent must:

- **context-off:** "You may use ONLY the warehouse MCP tools (`list_tables`,
  `describe_table`, `read_query`). Do NOT read the `analytics-context` repo or any
  context files. Issue **read-only SQL only** (SELECT; never DDL/DML). Answer the
  question and return: the number, the exact SQL you ran, your assumptions, and the
  tables you used."
- **context-on:** identical, but also: "First read this domain's `reference.md`,
  `metrics.yaml`, `entities`, and `evals/seeds/` for the domain, and follow them."

Return shape from each agent: `{ value, sql, assumptions[], tables[] }`.

Write each agent's full output as a trace to
`evals/runs/<timestamp>/<question-slug>.{off,on}.md`. These are generated artifacts
(gitignored) — they're how the analyst audits *why* an answer differed.

## 4. Verify one question at a time

The agents ran in parallel; verification is sequential because a human is in the
loop. For each question, show the contrast plainly:

```
Q: What is our collection rate by payer, last quarter?
  context-off → 0.97   (aggregated Cigna across TX+FL, no 45-day cutoff)
  context-on  → 0.92   (state-split payers, sessions ≥ 45 days)
```

Then ask for the truth: *"What does your dashboard show for this, and as of what
date?"* Record the value and the `as_of` date. (Let the analyst set the tolerance —
"close enough" is their call, not yours.)

## 5. On a match (on-answer == dashboard)

1. Show the assumptions and the SQL the context-on agent used, and ask the analyst
   to bless them: *"Here's the query and what it assumed — good to save these as the
   answer key?"*
2. Write/upgrade the seed:
   - `provenance: dashboard`, `status: confirmed`
   - `expected.kind: value_at_snapshot`, `value: <dashboard number>`, `as_of: <date>`
   - `intent:` ← the confirmed assumptions (the disambiguation it got right)
   - `ir:` ← the decomposition the verified query actually used — `metric` (the
     `metrics.yaml` name), `dimensions`, `filters`, `time_window` (absolute
     `{start, end}` is fine here; `as_of` pins the seed). You have the query in
     front of you at this moment, so record its structure, not just its prose —
     this is what makes the seed and the production decomposition the same object.
   - write the blessed context-on SQL to `evals/verified/<seed-name>.sql` (a LOCAL,
     gitignored sidecar — **do not commit the SQL**) and point the seed at it with
     `verified_query_file: evals/verified/<seed-name>.sql`. The seed (committed) holds
     the answer key (value + date); the SQL (local) stays out of git because it goes
     stale fast and must not be cloneable from a published context repo.
   This is the strongest seed you can produce: number + date + reusable (local) SQL.
3. **Offer to promote the form into context.** If the blessed query's exact form is
   itself the hard-won knowledge (the dedup, join path, or mandatory clause the
   off-agent missed), offer: *"Want me to save this shape as a query pattern in the
   domain's reference.md?"* On yes, distill it — keep model/column names, replace
   literal values with `<placeholders>`, lead with a one-line `Without this: …`
   naming the failure it prevents — and add it under "Common query patterns"
   (rules in `reference-doc-skeleton.md`). The runnable original stays only in the
   sidecar; what's committed is the form, not the report.

## 6. On a mismatch (on-answer != dashboard)

Don't paper over it — this is the most valuable moment. Ask: **"Why doesn't it
match?"** The analyst's answer names a missing caveat or disambiguation. Harvest it
the Stage-4 way:

- add the caveat to the domain's `known-issues.md` and an `IF … DO NOT …` routing
  trigger to its `reference.md`, and
- write a `provenance: correction`, `status: confirmed` seed whose `expected.kind:
  sql_shape` encodes the *correct* handling (`must_include` / `must_exclude`),
  with an `ir:` block recording the correct decomposition (relative
  `time_window` — the value isn't pinned, so the window must stay evergreen).
- Do **not** write the wrong SQL to `evals/verified/` or set `verified_query_file`.
  Leave the value unpinned until a re-run verifies it.

A failed live eval thus feeds straight back into the context — the loop closes in
the same session.

## 7. Print the live delta summary

Close with the in-session version of the harness report (`INTERFACE.md`):

```
Domain: session-financials   (verified live, 5 questions)
  context-off → 40%   (2/5 matched the dashboard)
  context-on  → 100%  (5/5)        +60 pts

  Context that earned its keep this round:
    • collection rate   off aggregated Cigna across states; on split TX/FL
    • active providers  off used dim_provider; on used the CPC grain
  Still wrong with context on → folded into corrections above.
```

The durable outputs are the seeds and the updated `reference.md` / `known-issues.md`;
the summary itself is ephemeral.

## Later: remote execution

The orchestration above is mechanism-agnostic. Today the answering agents are
in-session subagents. The same prompts can later be launched as remote runs
(agent-harness / Modal) with distinct MCP configurations for the off vs on runs —
only the launch step changes; steps 4–7 stay identical.
