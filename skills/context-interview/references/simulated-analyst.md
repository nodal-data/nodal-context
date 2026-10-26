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

At startup (Stage 0), use the explicit marker path in the launch prompt, or check
for `.sim-analyst.json` at the current project/context repo root. If neither is
present, run the normal human interview. Read only the marker, not the brief:

```json
{ "responses": "/abs/path/responses.md", "log": "/abs/path/sim-analyst-log.md",
  "mode": "non-interactive", "run_id": "local-run-id" }
```

- `responses` — the analyst knowledge brief (a **sibling** of the repo, deliberately
  outside it).
- `log` — local question/reply/escalation transcript maintained by the helper.
- `mode` — `interactive` (default) or `non-interactive`. An unresolved question
  asks the real human in interactive mode; it pauses non-interactive mode.
- `run_id` — optional run identity. `state` optionally overrides the sibling
  `.state.json` path derived from `log`; it preserves pending questions and human
  attestations. Log and state stay beside the private brief, outside the project.

Then run every stage in this mode, including family/alias selections, method
decisions, open decisions and Stage 6 choices. Use
`scripts/simulated_analyst.py pending --marker MARKER` on resume before asking a
new question. After scaffolding or changing directories, keep using the explicit
marker or its handed-off copy. Never fall silently back to human mode.

The tracked clean-room harness puts the same marker in the starting project and
the context destination before launch. For other entry points, pass
`--sim-marker MARKER` to `scripts/scaffold.py`, or run the bundled helper:

```bash
python3 scripts/simulated_analyst.py handoff --marker /absolute/path/.sim-analyst.json --root ../analytics-context
```

This copies only pointers, never the brief. Resolve the helper relative to the
loaded skill before scaffolding; use the repo-local helper afterward. A mismatched
existing marker is an error, not permission to replace another test run.

## The loop (per question)

For each question you would otherwise put to the human:

1. **Do NOT read the brief yourself.** Integrity of the test depends on the
   interviewer eliciting, not peeking — only the responder subagent may open it.
2. Use the host's available delegation tool to spawn an **isolated responder
   subagent** ("simulated analyst") with:
   - the exact question (and just enough stage context to answer it),
   - the brief path from `responses`,
   - these instructions: *"Read this brief. You are the analyst being interviewed.
     Answer ONLY from the brief. If it clearly covers the question, reply
     `CONFIDENT: <answer>`. If it doesn't, or you'd have to guess, reply
     `NOT_CONFIDENT: <what's missing>`. Be conservative — prefer NOT_CONFIDENT over
     inventing."*
3. Interpret the reply:
   - **`CONFIDENT: …`** → use the answer to continue drafting without surfacing
     each question to the human. Keep every simulator-only domain, entity, metric,
     method, pattern and seed proposed working-branch content, with no `approver` or `confirmed_at`.
     Confidence advances the interview; it never confirms a definition.
   - **`NOT_CONFIDENT: …`** → **escalate**: ask the real human this question at the
     terminal in interactive mode, then continue with their answer. In
     non-interactive mode record the pending question and stop. Missing responder
     capability or a malformed reply also stays pending; do not read the brief
     yourself or guess to complete the run.
4. **Log it** — save the question and reply to ignored local files and invoke the
   helper with a stable question ID and stage. Repeating the same exchange is
   idempotent; a changed answered question needs a new ID. The shared state is
   authoritative and the Markdown log can be regenerated from it.

```bash
python3 scripts/simulated_analyst.py record --marker MARKER --id revenue-001 --stage 2 \
  --question-file .nodal/question.txt --reply-file .nodal/reply.txt
```

For the real human's reply to a pending question, use the same ID and question
with `--source human --reviewer 'Actual human name'`. This records an answer; it
does not automatically confirm all related artifacts. Only explicit real-human
approval of a particular definition/seed permits normal confirmation metadata.
After that reviewed edit, record the matching artifact receipt:

```bash
python3 scripts/simulated_analyst.py attest-human --marker MARKER --root . \
  --id metric:revenue.net_revenue --reviewer 'Actual human name'
```

Never call `attest-human` on the basis of a simulated answer. It writes only a
local attestation for already-authored bytes and cannot change status or approval
fields. Changed artifacts require renewed review; approval of one object does
not approve its dependents. Historical approval metadata on a later draft must
also be supported by a real-human receipt.

**Real-world actions are never simulated.** Anything that requires hands — running
a privilege grant, copying a repo into the sandbox, re-authing a connection — is
addressed to the real human in your user-facing status output, never routed
through the consult-and-log loop. The sim analyst answers questions; it cannot
act, and an action buried in the log is an action that never happens.

Batching optimization (optional): when a stage elicits a list (terminology, entities,
caveats — see `interview-flow.md`), you may pass the whole pending list to one
subagent consult instead of one call per item, to cut round-trips. Same
confidence requirement for every item. When recording the batch as one question,
instruct the responder to begin the entire reply with exactly `CONFIDENT:` only
if every item is covered by the brief; otherwise begin with `NOT_CONFIDENT:` and
name the missing items. Put numbering after that first prefix, never before it.
For example: `CONFIDENT: 1a. ... 1b. ...`. The helper accepts one exchange per
record call, not a numbered list of independent status-prefixed replies. If
recording items separately, each item's verbatim reply must independently begin
with its status prefix. A `CONFIDENT:` header cannot hide a `NOT_CONFIDENT:` item.

Do not rewrite a malformed reply into a confident one, reset shared state, or
use another question ID to bypass a pending human question. Preserve the original
exchange and follow the pending-question protocol above.

Forced-choice questions pass through the same contract: give the responder the
full option list *with each option's evidence*, and it answers
`CONFIDENT: <option or its own wording>` only if the brief actually
discriminates between the candidates. A brief that supports the frame but not
the choice is precisely a `NOT_CONFIDENT` — escalate. The responder must never
default to the most-cited option.

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
  no-statistics discipline remain the same. Draft-only simulation is the explicit
  exception to automatic progress toward confirmed artifacts: only a real human
  may promote an object. Do not emit a confirmed negative/snapshot seed from a
  simulated answer either.

## Output and verification

Use ACF 0.3 per-metric YAML, method frontmatter and valid draft seeds. Skip
unavailable warehouse/dashboard/notebook checks explicitly while retaining useful
draft context. A responder cannot attest that a notebook ran, a dashboard matched,
authentication succeeded or a result was verified. Do not put invented numeric
values in a snapshot seed. Keep briefs, transcripts and state local.

Notebook import is available during this quick flow, but simulated method-review
answers still produce drafts. Do not make notebook execution, dashboard access or
the full release matrix prerequisites for finishing a useful draft interview.
Record every deferred verification in the summary and any known notebook case
bindings in ignored local candidate files; only real review/execution can clear
the corresponding gates.

After each host launch, including a pause before scaffolding, the clean-room
harness writes private `simulation-summary.json` beside its projects. It lists
the generated context path, draft metrics/methods, exchange log, pending human
questions, open decisions and verification follow-ups. Validation and execution
verification are separate. For a direct interview outside that harness, run:

```bash
python3 scripts/simulated_analyst.py summary --marker MARKER --root .
```

This reads context and interview state, never the private brief or a notebook.
Treat its output as private; pending questions can contain customer information.

Run `scripts/simulated_analyst.py check --marker MARKER --root .` before closing.
The clean-room harness checks the same boundary and rejects confirmed objects
without matching explicit human receipts. Receipt checks are operator attestations,
not proof of human identity or external execution. No actual approval is created
by naming the simulator as an approver.

Draft-selection evaluations use `python -m eval_harness.run --status draft` and
must remain labeled draft/simulated, excluded from human-verified coverage. The
normal confirmed baseline remains unchanged. Pending questions survive the
clean-room `--resume` path; non-interactive harness exit code 3 means paused with
pending human input, never successful completion.
