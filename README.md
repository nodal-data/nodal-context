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
([`eval_harness/INTERFACE.md`](./eval_harness/INTERFACE.md)) reads ACF, Kaelio
`ktx` YAML, dbt models/docs, or raw markdown, normalizes them, and measures the
delta the same way. Bring whatever context you already have.

## Quickstart

Before the interview, give the context builder the two things it works from. Both are
optional-to-have-perfect but make the interview **faster and more accurate** — the agent
verifies definitions against live data and reads your existing transformations instead of
guessing.

**1. Connect a warehouse over MCP (required).** The interview verifies answers against
your live warehouse, and the generated repo's `data-question` skill queries it — both need
**read-only** warehouse access. Pick the MCP server for your warehouse and add it to your
agent:

| Warehouse | MCP server |
|---|---|
| Snowflake | [Snowflake MCP](https://github.com/Snowflake-Labs/mcp) |
| BigQuery | [MCP Toolbox for Databases](https://github.com/googleapis/genai-toolbox) (Google) |
| Redshift | [AWS Labs MCP servers](https://github.com/awslabs/mcp) (Redshift) |
| Databricks | [Databricks MCP](https://github.com/databricks/databricks-mcp) |
| Other / general | [Model Context Protocol servers](https://github.com/modelcontextprotocol/servers) |

Use a **read-only role/credential** — the interview and the data-question skill only ever
`SELECT`. See your agent's MCP docs (e.g. Claude Code: `claude mcp add`) for wiring it in.

**2. Clone your dbt repo locally (recommended).** If you use dbt, `git clone` your dbt
project into a sibling directory and start the interview with both repos visible to the
agent. The interview reads your `models/`, `schema.yml`, and metric definitions as a
**draft to confirm** — so the analyst corrects real definitions instead of describing them
from scratch, and the generated `lineage:` pointers reference actual dbt models.

```bash
# 1. Get the tool. The interview skill reads SPEC.md, template/, schemas/, and
#    scripts/ from the repo root, so clone the WHOLE repo (not just the skill folder).
git clone https://github.com/nodal-data/nodal-context.git
cd nodal-context

# 2. Open your agent here (Claude Code / Codex / Cursor) and say:
#    "Build my analytics context."  → the context-interview skill takes over.
#    (The skill is already discoverable in-repo via .claude/skills/.)
#    It writes a reviewable ../analytics-context/ repo as a SIBLING of this clone
#    (git-initialized; the tool repo stays read-only) and, at the end, offers to
#    push it to GitHub.

# 3. After the first domain, see the delta:
#    "Run the eval delta on session-financials."

# 4. Use the context day-to-day: cd into the generated repo and ask Claude Code a
#    real question — see that repo's README.md (Claude Code base case + Codex).
```

The generated `../analytics-context/` is your deliverable — its own git repo. The cloned
`nodal-context/` tool repo stays read-only; keep it to re-run the interview for more
domains later, or delete it once the context repo is pushed.

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
├── eval_harness/               # OSS eval runner + its contract (INTERFACE.md, README.md)
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
question is instant. An optional second connector exposes your **dbt/warehouse
lineage** the same way, so the agent can check *how* a metric is computed, not just
what it means.

There are **three ways** to serve it:

- **Build your own** — self-host a small read-only MCP server against the raw repo.
  Always free, no lock-in.
- **Launch on Nodal (hosted)** — the low-cost, self-serve path: subscribe, add a
  read-only GitHub token in the admin, share the endpoint. **No database connection
  needed** — Nodal serves the context repo, not your data.
- **Run it in your own cloud/VPC** — for data-residency or security requirements;
  **contact sales**.

Auth, escalation routing, usage logging, and the learning loop are the managed product —
a convenience for team-scale distribution, not a lock on the format: the files stay open
and self-hosting is always free. The generated repo ships a `SHARING.md` with the tool
surface and the 3-step hosted setup.

## Keep context in sync with your dbt repo

Context goes stale the moment a dbt model changes underneath it — a renamed column, a
redefined metric, a dropped table — and stale context is worse than none, because the
agent trusts it. The free CI contract catches this: the bundled `context-drift` workflow
flags, on every PR, when an upstream dbt model a domain depends on has changed, so a
human re-confirms the definition.

Nodal offers the **managed version of that loop**: connect your dbt repo and changes
there propagate into the business context automatically — the affected definitions are
re-drafted from the new dbt source and routed to the analyst to confirm (still
interview-built — a human owns every definition, the sync just keeps the draft current).
This rides on the same `lineage:` pointer ACF already keeps per domain. It's an
**optional, paid** add-on, deployable in your cloud/VPC or ours.

## The free / paid line, explicitly

| Capability | Where | Cost |
|---|---|---|
| Context format (ACF) | `SPEC.md`, `schemas/` | Free, Apache-2.0 |
| Interview skill | `skills/context-interview/` | Free |
| Eval-seed harvesting (interview → labeled pairs) | the skill | Free |
| One-shot eval delta (on/off, run locally) | the harness, self-run | Free |
| Self-hosted agent against the raw context files | your agent | Free |
| **Team-shared MCP endpoint (governed answers + escalation for non-technical users, auth, usage logging)** | Nodal (hosted) | **Paid** |
| **dbt-repo sync (auto-propagate dbt changes into the context, analyst-confirmed)** | Nodal (hosted) | **Paid** |
| **Trustworthy ground truth, continuous re-eval, drift detection, observability, correction harvesting** | Nodal (hosted) | **Paid** |

The hosted MCP endpoint is low-cost and self-serve. The dbt-repo sync and the
observability/eval system are how data teams keep context correct — and see who's asking
what — as they scale self-service analytics; for a demo, requirements, or pricing,
**contact sales** at info@nodaldata.io.

## License

Apache-2.0 (see `LICENSE`). The format and the interview are yours to keep.