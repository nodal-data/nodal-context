# Example Healthcare Company Analytics Context

This repo is Example Healthcare Company's **business context layer** for analytics
agents, in Analytics Context Format (ACF). It tells an AI agent what your terms mean,
which table is canonical, what the standard filters are, and where the landmines are
— so it answers data questions correctly instead of writing confidently-wrong SQL.

> This is a **worked example** shipped with `nodal-context` to show what a generated
> context repo looks like. It is built around one domain (`session-financials`) and a
> couple of eval seeds. A real repo is built by interviewing your analyst.

It was built by interviewing your analyst (the `context-interview` skill), and every
confirmed definition is also a labeled eval pair under `evals/seeds/`.

## Prerequisite: a warehouse MCP server

Answering a question requires the agent to run read-only SQL against your warehouse.
Configure a warehouse MCP server (e.g. Snowflake/BigQuery) in your agent before you
start — without it the agent can read this context but cannot fetch live numbers.

## Use it with Claude Code (base case)

```bash
cd analytics-context        # this repo
claude
```

Then ask a real data question — `CLAUDE.md` auto-loads from this directory and tells
the agent to route via the relevant `domains/<domain>/reference.md`, honor the
caveats, and query read-only.

Or make it a one-liner with the bundled skill:

```
/data-question "what was our collection rate by payer last quarter?"
```

## Use it with Codex / other agents

Open the agent with this repo available. Agents that read `AGENTS.md` (Codex, Cursor)
will find the same "Answering a data question" routing steps there — no skill needed.
If your agent doesn't auto-load either file, paste the routing steps from `AGENTS.md`
into your prompt.

## Keep it fresh

- Add a domain or correct a definition by **re-running the `context-interview`
  skill** — it resumes from `context.config.yaml` rather than starting over.
- Review every change **by PR**. The bundled `.github/workflows/` validate the YAML,
  flag unconfirmed `status: draft` entries, run the on/off eval delta, and detect
  drift when an upstream model changes.

## Push to GitHub

This repo is initialized as a git repo with an initial commit. To share it with your
team:

```bash
gh repo create example-healthcare-company-analytics-context --private --source . --push
# or, without the gh CLI:
git remote add origin git@github.com:<your-org>/<repo>.git
git push -u origin main
```

## Advanced: serve via MCP (planned)

Today agents read this repo from the filesystem. A planned option is a small
read-only MCP server that exposes each `domains/<domain>/reference.md` and
`company/terminology.md` as MCP **resources** plus a
`route_question(question) -> {domain, reference_md, caveats}` **tool** — mirroring the
Normalized Context Representation in the harness contract
(`eval-harness/INTERFACE.md`). Not required for the base case above.
