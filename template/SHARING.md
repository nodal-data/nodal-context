# Share this context with your team

This repo is Markdown + YAML that **[company] owns**. A single analyst can point their
own agent at these files and get governed answers for **free** — clone it, read it
locally, done. To put the same context in front of the *whole team* — so a non-technical
business user asks a question in their own agent and gets the answer the analyst would
give — serve it over **MCP** (Model Context Protocol). Start with the
**[MCP overview](https://docs.nodaldata.io/mcp/overview)** for how this works
end to end.

## What an MCP server exposes

An MCP server turns this repo into agent tools over two connectors:

- **Context connector** — reads this repo (index, regex search, file fetch, browse)
  plus governed answering: retrieve the right definitions and canonical queries,
  answer when confident. 
- **Lineage connector (optional, no extra cost)** — your dbt/warehouse lineage the same way. The
  context connector says *what a term means*; the lineage connector says *how it's
  computed*.

See the full **[tool reference](https://docs.nodaldata.io/mcp/tools)** for the exact
tool names and signatures.

## Three ways to serve it

### 1. Build your own — self-host, free
These are read-only file/grep tools over this repo — a small MCP server. Start from the
MCP docs at https://modelcontextprotocol.io (plus your agent's MCP setup guide). The
files stay yours; there's no lock-in.

### 2. Launch on Nodal (hosted) — low-cost, ~2 minutes, no database connection
The fastest way to share with the whole team. **No warehouse/database connection
required** — Nodal serves this context repo, not your data. In short: subscribe, add a
**read-only GitHub token** scoped to this repo in the Nodal admin, and share the
endpoint — your team adds it in their own agent and asks questions in plain language.
You get multi-user auth, simple evaluations, and usage logging out
of the box.

Follow the current subscribe link, pricing, and endpoint in the
**[hosted setup guide](https://docs.nodaldata.io/mcp/share-with-your-team)**.

### 3. Run it in your own cloud/VPC — regulated / enterprise
For data-residency or security requirements, Nodal can build and maintain the MCP server
**inside your environment**. Contact sales: info@nodaldata.io.

## Keep it fresh + observability (enterprise)

As you roll out self-service analytics, keeping context correct — and knowing how it's
used — becomes the job. Nodal's enterprise system adds:

- **dbt-repo sync** — changes in your dbt models propagate into the affected definitions
  as drafts for your analyst to confirm, so context tracks the warehouse automatically.
- **Continuous evaluation + drift detection** — trustworthy ground truth and accuracy
  tracking on every change, so silent regressions get caught.
- **Observability** — who's asking what, where the agent escalates, and where context is
  thin.

This is the gold standard for data teams maintaining context at scale. Contact sales for
a demo, requirements, and pricing: info@nodaldata.io.

---

The files stay open and **self-hosting is always free**. The hosted and enterprise
options are conveniences for team-scale distribution and maintenance — not a lock on the
format. See the full free/paid line on
[docs.nodaldata.io](https://docs.nodaldata.io/enterprise/overview).
