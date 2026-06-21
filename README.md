# nodal-context

> The open-source, **interview-built** context layer for analytics agents — plus a
> format-agnostic harness that measures whether your context actually makes the
> agent more accurate.

---

## What this is

Pointing Claude, Codex (or any agent) at a warehouse and letting it write SQL feels like
self-service analytics until you notice the answers are confidently wrong. The fix
isn't a better model — it's **context**: what your terms mean, which table is
canonical, what the standard filters are, and where the landmines are.

`nodal-context` is two things:

1. **A context-layer format + an interview skill** that builds that context *with*
   your analyst, one domain at a time — and writes it to a git repo your team
   reviews by PR. This part is **free and open source (Apache-2.0)**. Take it,
   fork it, never talk to us.

2. **An eval seam** that turns the same interview into a measurement: how accurate
   is your agent *with* the context vs *without* it, and how far is it still from
   *ground truth*. The format for evals is open; the **hosted measurement,
   continuous re-evaluation, drift detection, and observability are the
   commercial product** (Nodal).

## Why interview-built, not auto-built

The obvious approach — and what most tools do — is to ingest your warehouse, dbt,
BI layer, and query history and *auto-generate* the context. We deliberately don't
lead with that, because the teams who've measured it found it doesn't work as a
source of truth:

- Anthropic's data team reported that auto-generating metric definitions from
  raw tables and query logs "encoded the very ambiguities we were trying to
  eliminate" and was **net-negative on evals** vs a smaller human-curated layer.
- They also gave an agent grep access to thousands of prior queries and accuracy
  moved **less than a point** — the information was present, the agent saw it, and
  it still didn't resolve the question to the right entity.
- [Reference work from Anthropic](https://claude.com/blog/how-anthropic-enables-self-service-data-analytics-with-claude)
- Other data agents find similar conclusions: [Meta](https://claude.com/blog/how-anthropic-enables-self-service-data-analytics-with-claude) and [Ramp](https://engineering.ramp.com/post/meet-ramp-research)

Their conclusion: **generate the documentation with the model, but have a human own
the definition.** That's exactly what the interview does. We *do* auto-extract
schema and dbt as a **draft to correct** (so the analyst isn't staring at a blank
page) — but the analyst's confirmations, not the extraction, are what we trust.

The bonus: every disambiguation the analyst makes in the interview ("active client
means X, not Y") is simultaneously a context entry **and** a labeled eval pair. The
act of building context is the act of harvesting ground truth.

## The format is readible and open-source (markdown + YAML )

This repo defines a context format (ACF — see [`SPEC.md`](./SPEC.md)). But you are
**not required to use it** to use the measurement seam. The harness
([`eval-harness/INTERFACE.md`](./eval-harness/INTERFACE.md)) reads ACF, Kaelio
`ktx` YAML, dbt models/docs, or raw markdown, normalizes them, and measures the
delta the same way. Bring whatever context you already have.

## Quickstart

**Prerequisite:** a **warehouse MCP server** (e.g. Snowflake/BigQuery) configured in
your agent. The interview verifies answers against your live warehouse, and the
generated repo's `data-question` skill queries it — both need read-only warehouse
access.

```bash
# 1. Get the interview skill into your agent (Claude Code / Codex / Cursor)
npx degit nodal-data/nodal-context/skills/context-interview .claude/skills/context-interview
#    (or copy skills/context-interview/ into your agent's skills dir)

# 2. In your agent, from your data project:
#    "Build my analytics context."  → the context-interview skill takes over.
#    It writes a reviewable ./analytics-context/ repo (git-initialized) and, at the
#    end, offers to push it to GitHub.

# 3. After the first domain, see the delta:
#    "Run the eval delta on session-financials."

# 4. Use the context day-to-day: cd into the generated repo and ask Claude Code a
#    real question — see that repo's README.md (Claude Code base case + Codex).
```

## Repo layout

```
nodal-context/
├── SPEC.md                     # the Analytics Context Format (ACF) — the standard
├── skills/context-interview/   # the interview skill (the free wedge)
│   ├── SKILL.md
│   └── references/             # the interview state machine + skeletons + harvesting
├── schemas/                    # JSON Schemas that make the YAML CI-checkable
├── template/                   # the empty scaffold the interview fills in
├── examples/example-healthcare-company/         # a worked example in the ACF format
├── eval-harness/INTERFACE.md   # format-agnostic seam → on/off/perfect delta
└── .github/workflows/          # validate context, detect drift, run eval delta on PR
```

## Sharing it across your team (MCP)

A context repo is just Markdown + YAML, so a single analyst can point their own agent
at the files and get governed answers **for free** — clone it, read it locally, done.
That works great for one person on one machine.

To put the same context in front of the *whole team* — so a non-technical business
user asks a question in their own agent and gets the answer the analyst would give —
connect over **MCP**. A hosted MCP endpoint serves the context layer (and the query
hub it grows into) as tools any agent can call: it retrieves the right definitions and
canonical queries for a question, answers when it's confident, and **escalates to the
analyst when it isn't** — then learns from the verified answer so the next identical
question is instant.

Running that shared endpoint — access control, escalation routing, and usage logging
across the team — is **optional and paid**. It's a convenience for team-scale
distribution, not a lock on the format: the files stay open, and self-hosting an agent
against the raw repo is always free.

## The free / paid line, explicitly

| Capability | Where | Cost |
|---|---|---|
| Context format (ACF) | `SPEC.md`, `schemas/` | Free, Apache-2.0 |
| Interview skill | `skills/context-interview/` | Free |
| Eval-seed harvesting (interview → labeled pairs) | the skill | Free |
| One-shot eval delta (on/off, run locally) | the harness, self-run | Free |
| Self-hosted agent against the raw context files | your agent | Free |
| **Team-shared MCP endpoint (governed answers + escalation for non-technical users, auth, usage logging)** | Nodal (hosted) | **Paid** |
| **Trustworthy ground truth, continuous re-eval, drift detection, observability, correction harvesting** | Nodal (hosted) | **Paid** |

## License

Apache-2.0 (see `LICENSE`). The format and the interview are yours to keep.