# nodal-context

> The open-source, **interview-built** context layer for analytics agents — plus a
> format-agnostic harness that measures whether your context actually makes the
> agent more accurate.

📖 **Docs:** [docs.nodaldata.io](https://docs.nodaldata.io) · 🌐 **Website:** [nodaldata.io](https://nodaldata.io)

---

## What this is

Pointing an AI Agent (Claude, Codex, Gemini, or any other) at a warehouse and letting it write SQL feels like
self-service analytics until you notice the answers are confidently wrong. The fix
isn't a better model — it's **context**: what your terms mean, which table is
canonical, what the standard filters are, and where the landmines are.

`nodal-context` is three things, in the order teams adopt them:

1. **Build it — the context format + the interview skill.**
   *Free, open source (Apache-2.0).*
   The skill builds context *with* your analyst, one domain at a time, and writes
   it to a git repo your team reviews by PR. Two depths, one flow: the full
   multi-stage interview, or a **~30-minute fast pass** that confirms a domain's
   five highest-leverage answers live and drafts the rest. Take it, fork it,
   never talk to us.

2. **Share it — the hosted MCP endpoint.**
   *Self-serve, low-cost: subscribe and launch in minutes.*
   Puts the same context in front of the whole team: any agent gets governed
   answers from the repo. Merge a PR and every consumer is current — no
   redistributing files. Self-hosting a read-only server on the raw files is
   always free; the hosted endpoint adds auth, escalation routing, and usage
   logging. See "Sharing it across your team" below. We can also build an MCP
   server in your cloud environment if your prefer.

4. **Keep it correct — the eval + maintenance system.**
   *Enterprise: [contact us](mailto:info@nodaldata.io).*
   The same interview mints ground-truth eval seeds, so you can measure your
   agent *with* context vs *without* vs *ground truth*. The seed format and a
   one-shot local runner are open; the hosted system adds dynamic evals, continuous
   re-evaluation, drift detection, dbt-repo sync (an upstream model change
   re-drafts the affected definitions for the analyst to confirm), and
   observability into who's asking what.

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
- Other data agents find similar conclusions: [Meta](https://medium.com/@AnalyticsAtMeta/inside-metas-home-grown-ai-analytics-agent-4ea6779acfb3) and [Ramp](https://engineering.ramp.com/post/meet-ramp-research)

Their conclusion: **generate the documentation with the model, but have a human own
the definition.** That's exactly what the interview does. We *do* auto-extract
schema and dbt as a **draft to correct** (so the analyst isn't staring at a blank
page) — but the analyst's confirmations, not the extraction, are what we trust.

The bonus: every disambiguation the analyst makes in the interview ("active client
means X, not Y") is simultaneously a context entry **and** a labeled eval pair. The
act of building context is the act of harvesting ground truth.

## Two depths: the full interview, or a 30-minute fast pass

Skill-based extractors (e.g. Anthropic's `data-context-extractor` for Claude
desktop) set a fair market expectation: an analyst should get useful context in
about half an hour. The interview meets that budget without giving up governance.
Say **"fast pass"** (or "I only have 30 minutes") and the same interview runs on a
five-question budget for one domain — the grain of the canonical table, the one
ambiguous entity, the top 2–3 metrics, the standard hygiene filter, and the one
silent failure — verifies a few answers live against your warehouse, and leaves
everything unasked as reviewable `status: draft` stubs.

The difference from a quick skill builder is what you keep: every confirmed answer
is still **human-owned**, still emits an **eval seed**, and the domain is
**depth-stamped** ("five questions deep, N drafts open") so speed never
masquerades as coverage. The full interview is the same flow without the budget —
and the fast pass's punch list (what the agent still gets wrong with context on)
tells you exactly which domains deserve it. Already built a data skill with a
quick extractor? The harness grades it as-is (`--adapter skill`), and the fast
pass is the cheapest way to mint the seeds that grade it.

## The format is readable and open-source (Markdown + YAML)

This repo defines a context format (ACF — see [`SPEC.md`](./SPEC.md)). But you are
**not required to use it** to use the measurement seam. The harness
([`eval_harness/INTERFACE.md`](./eval_harness/INTERFACE.md)) reads ACF, Kaelio
`ktx` YAML, dbt models/docs, raw markdown, or an agent data-analysis skill (e.g.
one generated by Anthropic's `data-context-extractor` — folder or packaged zip),
normalizes them, and measures the delta the same way. Bring whatever context you
already have.

## Quickstart

Before the interview, set up the two things it works from. Neither needs to be
perfect, but both make the interview **faster and more accurate**: the agent verifies
definitions against live data and reads your existing transformations instead of
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

# 2. Open your client agent here (Claude Code / Codex / Cursor) and say:
#    "Build my analytics context."  → the context-interview skill takes over.
#    Short on time? Say "fast pass" — five core questions, a live check,
#    the rest drafted for a later session.
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

This is product #2 above — the self-serve one. A context repo is just Markdown +
YAML, so a single analyst can point their own agent at the files and get governed
answers **for free**: clone it, read it locally, done. That works great for one
person on one machine.

To put the same context in front of the *whole team* — a non-technical business
user asks a question in their own agent and gets the answer the analyst would
give — connect over **MCP**. A hosted endpoint serves the context layer (and the
query hub it grows into) as tools any agent can call. It retrieves the right
definitions and canonical queries, answers when it's confident, and **escalates
to the analyst when it isn't** — then learns from the verified answer, so the
next identical question is instant. An optional second connector exposes your
**dbt/warehouse lineage**, so the agent can check *how* a metric is computed,
not just what it means.

Three ways to serve it:

- **Launch on Nodal (hosted)** — the self-serve path: subscribe, paste a
  read-only GitHub token into the admin, share the endpoint. Three steps, minutes,
  low-cost. **No database connection needed** — Nodal serves the context repo,
  not your data.
- **Build your own** — self-host a small read-only MCP server against the raw
  repo. Always free, no lock-in.
- **Run it in your own cloud/VPC** — for data-residency or security requirements;
  **contact sales**.

Auth, escalation routing, usage logging, and the learning loop are the managed
product — a convenience for team-scale distribution, not a lock on the format:
the files stay open and self-hosting is always free. The generated repo ships a
`SHARING.md` with the tool surface and the 3-step hosted setup.

**Claude-desktop and skill.md shop instead?** Compile the repo into a distributable skill snapshot:

```bash
python3 scripts/compile_skill.py path/to/analytics-context --zip
```

That emits a `<company>-data-analyst/` skill (SKILL.md + references/) an admin can
upload to claude.ai / Claude desktop — org-provisioned skills update centrally. The
output is a **stamped snapshot** (`compiled from repo@sha`), not a second source of
truth: regenerate it after every merge. It round-trips through the eval harness's
`skill` adapter with the same domain names, so the same seeds grade both the repo and
the compiled skill. MCP remains the live, always-current path; the skill is a cache
for reach.

## Keep context in sync with your dbt repo

Context goes stale the moment a dbt model changes underneath it — a renamed column, a
redefined metric, a dropped table — and stale context is worse than none, because the
agent trusts it. The free CI contract catches this: the bundled `context-drift` workflow
flags, on every PR, when an upstream dbt model a domain depends on has changed, so a
human re-confirms the definition.

Nodal offers the **managed version of that loop**: connect your dbt repo and changes
there propagate into the business context automatically — the affected definitions are
re-drafted from the new dbt source and routed to the analyst to confirm (still
interview-built: a human owns every definition, the sync just keeps the draft current).
This rides on the same `lineage:` pointer ACF already keeps per domain. It's part of
the **enterprise tier** (product #3), deployable in your cloud/VPC or ours —
[contact us](mailto:info@nodaldata.io).

## The free / paid line, explicitly

| Capability | Where | Cost |
|---|---|---|
| Context format (ACF) | `SPEC.md`, `schemas/` | Free, Apache-2.0 |
| Interview skill (full or fast pass) | `skills/context-interview/` | Free |
| Eval-seed harvesting (interview → labeled pairs) | the skill | Free |
| One-shot eval delta (on/off, run locally) | the harness, self-run | Free |
| Compiled skill snapshot for Claude desktop | `scripts/compile_skill.py` | Free |
| Self-hosted agent against the raw context files | your agent | Free |
| **Team-shared MCP endpoint (governed answers, auth, usage logging)** | Nodal (hosted) | **Paid — self-serve** |
| **dbt-repo sync (dbt changes re-drafted into context, analyst-confirmed)** | Nodal (hosted) | **Paid — enterprise** |
| **Trustworthy ground truth, continuous re-eval, drift detection, observability, correction harvesting** | Nodal (hosted) | **Paid — enterprise** |

The **hosted MCP endpoint is the self-serve entry point**: subscribe, connect the
repo, share the endpoint — minutes, no sales call. The **eval/observability system
and dbt-repo sync are enterprise** — they're how data teams keep context correct,
and see who's asking what, as self-service analytics scales; for a demo,
requirements, or pricing, **contact us** at info@nodaldata.io. Learn more at
[nodaldata.io](https://nodaldata.io) or [docs.nodaldata.io](https://docs.nodaldata.io).

## License

Apache-2.0 (see `LICENSE`). The format and the interview are yours to keep.
