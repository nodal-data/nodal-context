# Simulated-Analyst Mode (testing only)

A test harness for iterating on the skill without re-answering every question by
hand. When active, a **subagent answers the interview's questions from a knowledge
brief**, and you only ask the *real* human when the brief doesn't confidently cover
something.

> **This is a testing convenience, not a way to build real context.** The
> simulated analyst's answers are NOT human confirmations. Context and seeds produced
> in a simulated run are **test artifacts** — they must not be treated as shippable
> confirmed context. The product's rule still holds: a real human owns every
> definition. Use this only to exercise the skill's flow.

## Activation

At startup (Stage 0), check for a `.sim-analyst.json` marker at the context repo
root (the cwd). If it's absent, ignore this file entirely and run the normal
human-answered interview. If present, read it:

```json
{ "responses": "/abs/path/responses.md", "log": "/abs/path/sim-analyst-log.md" }
```

- `responses` — the analyst knowledge brief (a **sibling** of the repo, deliberately
  outside it).
- `log` — append a transcript of the run here.

Then run every stage in this mode.

## The loop (per question)

For each question you would otherwise put to the human:

1. **Do NOT read the brief yourself.** Integrity of the test depends on the
   interviewer eliciting, not peeking — only the responder subagent may open it.
2. Spawn a **Task subagent** ("simulated analyst") with:
   - the exact question (and just enough stage context to answer it),
   - the brief path from `responses`,
   - these instructions: *"Read this brief. You are the analyst being interviewed.
     Answer ONLY from the brief. If it clearly covers the question, reply
     `CONFIDENT: <answer>`. If it doesn't, or you'd have to guess, reply
     `NOT_CONFIDENT: <what's missing>`. Be conservative — prefer NOT_CONFIDENT over
     inventing."*
3. Interpret the reply:
   - **`CONFIDENT: …`** → treat it as the analyst's answer. Proceed silently (don't
     surface the question to the human). Apply the same draft/confirmed rules you
     normally would.
   - **`NOT_CONFIDENT: …`** → **escalate**: ask the real human this question at the
     terminal, exactly as in a normal interview, then continue with their answer.
4. **Log it** — append to the `log` file: stage, question, `auto` vs `escalated`, the
   answer used, and (for escalations) the human's reply. One block per question, so
   the run is auditable.

Batching optimization (optional): when a stage elicits a list (terminology, entities,
caveats — see `interview-flow.md`), you may pass the whole pending list to one
subagent consult instead of one call per item, to cut round-trips. Same
CONFIDENT/NOT_CONFIDENT contract per item.

## `responses.md` format (the brief)

Freeform Markdown the responder reasons over — robust to reworded questions. Cover
what the interview asks about; leave gaps where you *want* escalation to the human.
Your live brief is `responses.md` (gitignored — it may hold customer-confidential
detail, so it never gets committed). Suggested sections:

```markdown
## Business        # what the company sells, who pays, the unit of value
## Warehouse       # platform(s); dbt project location
## Domains         # dashboards/areas, the canonical table + grain of each
## Metrics         # definitions in business terms (no statistics)
## Entities        # disambiguations: "provider" = individual not company; "active" = …
## Caveats         # silent-failure filters, timing effects, look-alike tables
## Overrides       # optional exact Q→A pairs that win over the prose above
```

The `## Overrides` section, if present, takes precedence for exact-match questions;
everything else is answered from the prose.

## What stays the same

- Stage order, the questions themselves, seed harvesting, and the
  draft-vs-confirmed/no-statistics discipline are all unchanged — you are only
  swapping *who answers*. A NOT_CONFIDENT escalation is the normal human question.
