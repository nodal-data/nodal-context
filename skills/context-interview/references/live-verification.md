# Stage 5 — Live Verification

The payoff stage. You've captured a domain; now *show the analyst the context
works* before they commit to more. Answer real questions against their live
warehouse twice — once with the context off, once on — and have the analyst confirm
the on-answer against a source they already trust (a dashboard). For a notebook
reference, follow `notebook-verification.md` for a fresh reference run and an
independent method answer on identical pinned inputs; a context-off run is optional
there. Every reviewed dashboard confirmation
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

For every analyst prompt, including pre-flight, dashboard confirmations, and
discrepancy follow-ups, use **process answer → update agenda and counts → display
progress → ask next question**. For a question or selection tool, send the line
in a visible assistant message immediately before the call, even if unchanged.
Use the verification format or missing-count fallback in `session-progress.md`;
background off/on execution does not require a new question or progress count.

## 1. Assemble the question set

Switch the session indicator to the verification format in `session-progress.md`:
cases reviewed out of the chosen set, with extra user questions estimated separately.
Count analyst-reviewed cases, not background off/on executions; report deferred
verification explicitly.

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
  cheaply — and if query history is still `deferred:` in Stage 0's disposition
  report and its blocker cleared (reauth done, `ACCOUNT_USAGE` grant landed),
  re-mine: fresh conflict groups are ready-made verification questions.
- Decide how the dashboard gets read. If a browser MCP binding is available (see
  `skills/dashboard-verify/references/browser-contract.md`) and the dashboard has a
  URL — from the domain's `domain.yaml` `dashboards:` entry, or ask — tell the
  analyst you'll read it yourself: *"I'll open the 'Collection Rate by Payer'
  dashboard in your browser and read the numbers — you just confirm them."* (If it
  needs a login, they log in; the skill waits.) If the saved target does not lead
  to the named dashboard, `dashboard-verify` asks the analyst once to open that
  exact dashboard in the connected, already signed-in browser and paste its normal
  address-bar URL, then retries directly. If that retry fails, or no URL is
  available, fall back to the human read: *"Have the 'Collection Rate by Payer'
  dashboard up — I'll ask you to read a number off it in a moment."* — and mention
  the one-time fix for next session:
  browser setup is optional and consent-based through `setup-nodal`. Respect the
  saved browser mode: `manual` goes directly to the human read without another
  setup offer; `automated` with a configured-but-unloaded binding asks for a
  restart rather than another install; `ask_when_needed` offers the connection
  once per `skills/dashboard-verify/references/browser-contract.md`. Either path
  feeds the same steps below.

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
  normalized per-metric definitions (including shared and transitive dependencies)
  and entities. For a method or new slice, also read the relevant `context.md` and
  method body. Follow effective readiness, filters, dimensions, ratio policy,
  method decisions and disclosures. Do not read `evals/seeds/`, verified queries,
  prior result traces, notebook code or reference outputs."

Use identical reviewed question bindings, time boundaries and input snapshot for
both agents. Keep their contexts independent; the orchestrator's answer keys and
dashboard evidence must not leak into either prompt. If fresh answering contexts
are unavailable, report this limitation rather than claiming an independent check.

Return shape from each agent: `{ value, sql, assumptions[], tables[], disclosures[] }`,
with actual execution evidence. Method answers additionally carry their resolved
metrics and parameters. A proposed query without a completed run is not a result.

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

Then get the truth from the dashboard:

- **Automated read** (browser binding available): invoke the `dashboard-verify`
  skill for the dashboard once — it emits a capture
  (`evals/captures/<timestamp>/…capture.json`) covering all its widgets; reuse
  that capture for every question on the same dashboard. Show the analyst the
  relevant value **with its extraction tier and the capture's filter state
  visible**, and have them bless it as the truth: *"Your dashboard shows 0.92
  for this (read exactly from the chart data; window Jan–Mar, sessions ≥ 45
  days) — is that the number you'd trust?"* A tier-4 (vision) value is called
   out as low-confidence before they bless it. Take `as_of` from the capture's
  `filter_state.as_of` (the dashboard's own freshness stamp). If missing, have the
  analyst establish data freshness; `captured_at` records when the screen was
  read, not necessarily the snapshot represented by its values.
- **Human read** (no binding): ask *"What does your dashboard show for this, and
  as of what date?"* and record the value and `as_of`.

Either way, the analyst sets the tolerance — "close enough" is their call, not
yours (and a display-rounded tile like "$5.9M" can never be held tighter than
its rounding; see `skills/dashboard-verify/references/reconcile.md`). With a
capture in hand, render the per-question diff as a reconciliation report
(reconcile.md) and write it to `<capture dir>/reconciliation.md` — it doubles as
the shareable "the system validated itself" artifact.

## 5. On a match (on-answer == dashboard)

1. Show the assumptions and the SQL the context-on agent used, and ask the analyst
   to bless them: *"Here's the query and what it assumed — good to save these as the
   answer key?"* (A legitimate rung-3 plain confirm — the truth anchor is the
   dashboard number the analyst just read, not your prose.)
2. Write/upgrade the seed:
   - `provenance: dashboard`; preserve the real reviewer and date in result-verification
     evidence. Omit authored approval fields; definition approval requires protected merge.
   - `expected.kind: value_at_snapshot`, `value: <dashboard number>`, `as_of: <date>`
   - `intent:` ← the confirmed assumptions (the disambiguation it got right)
   - `ir:` ← the decomposition the verified query actually used — `metric` (the
     per-metric canonical name), `dimensions`, `filters`, `time_window` (absolute
     `{start, end}` is fine here; `as_of` pins the seed). You have the query in
     front of you at this moment, so record its structure, not just its prose —
     this is what makes the seed and the production decomposition the same object.
     For a method use `method`, resolved `metrics` and bound `parameters` instead
     of a metric target; check its required disclosures and result relationships.
     Multirow snapshots need `key_columns` and agreed numeric tolerances. A numeric
     match alone does not establish the correct cohort or denominator.
   - capture the approved, actually executed SQL with `scripts/verified.py capture`
     in this verification operation (see `verified-sql.md`). It writes private
     `evals/verified/<seed-name>.sql` and immediately encrypts with the configured
     age/SOPS backend. Point the seed at the plaintext name via
     `verified_query_file: evals/verified/<seed-name>.sql`; only ciphertext is
     eligible for commit. The query remains outside context and answer prompts.
     Explicit `encryption: none` is local-only. On encryption failure, report
     `local_unpublished`; preserve the local query and repair encryption before
     claiming that a portable answer key exists. Do not silently use `none`.
   The snapshot records the approved value/date; successful encryption makes the
   reviewed replay query portable without exposing it as analytics context.
3. **Offer to promote the form into context.** If the blessed query's exact form is
   itself the hard-won knowledge (the dedup, join path, or mandatory clause the
   off-agent missed), offer: *"Want me to save this shape as a query pattern in the
   domain's reference.md?"* On yes, distill it — keep model/column names, replace
   literal values with `<placeholders>`, lead with a one-line `Without this: …`
   naming the failure it prevents — and add it under "Common query patterns"
   (rules in `reference-doc-skeleton.md`). The runnable original stays only in the
   sidecar; the context contains the form and the answer-key area may contain its
   encrypted runnable counterpart, never plaintext.

## 6. On a mismatch (on-answer != dashboard)

Don't paper over it — this is the most valuable moment. With a capture in hand,
check its `filter_state` against the query's window and filters *first*: the
mismatch often explains itself, and you lead with the explanation rather than a
question — *"Your dashboard filters to fully-elapsed months through Jul 31; my
query summed through Aug 12 — same number otherwise. Which framing should the
context encode?"* Only when the filter state doesn't account for it, ask the open
question: **"Why doesn't it match?"** Either way the analyst's answer names a
missing caveat or disambiguation. Harvest it the Stage-4 way:

- add the caveat to the domain's `known-issues.md` and an `IF … DO NOT …` routing
  trigger to its `reference.md`, and
- write a `provenance: correction`, merge approval seed whose `expected.kind:
  sql_shape` encodes the *correct* handling (`must_include` / `must_exclude`),
  with an `ir:` block recording the correct decomposition (relative
  `time_window` — the value isn't pinned, so the window must stay evergreen),
  after the analyst reviews that handling. Record review evidence without adding
  authored approval fields; protected merge grants approval. Keep unresolved
  explanations as working-branch review notes.
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
the summary itself is ephemeral. Calculate the delta only over comparable cases
actually graded on both sides; report missing, blocked and skipped checks
separately. Negative-kind escalation accuracy is separate from positive accuracy.

## Later: remote execution

The orchestration above is mechanism-agnostic. Today the answering agents are
in-session subagents. The same prompts can later be launched as remote runs
(agent-harness / Modal) with distinct MCP configurations for the off vs on runs —
only the launch step changes; steps 4–7 stay identical.
