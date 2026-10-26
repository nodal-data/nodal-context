# Share this context with your team

Read [GOVERNANCE.md](GOVERNANCE.md) for protected merge approval, live stale-state
checks, explicit branch testing and legacy conversion. New definitions omit
authored approval status; interview confirmation is evidence for review.


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
  plus governed answering: retrieves reviewed definitions, methods and query patterns
  to ground every answer.
- **Lineage connector (optional, no extra cost)** — your dbt/warehouse lineage the same way. The
  context connector says *what a term means*; the lineage connector says *how it's
  computed*.

See the full **[tool reference](https://docs.nodaldata.io/mcp/tools)** for the exact
tool names and signatures.

Serve an allowlist of authored context paths. Generic search, file fetch and
browse must exclude seed expectations/variants, `evals/verified/` (including
ciphertext), `evals/observed/`, captures, runs, `.nodal/`, source notebooks, private
briefs and key files. Ignored files are not automatically hidden from file tools.
Give a separate trusted evaluator access to answer keys only after generation;
keep evaluated seeds out of retrieval. Encrypted answer keys can travel with Git
without becoming answering context. Decryption and execution remain in the
customer's environment with customer-controlled keys and read-only credentials.

## Three ways to serve it

### 1. Build your own — self-host, free
These are read-only file/grep tools over this repo — a small MCP server. Start from the
MCP docs at https://modelcontextprotocol.io (plus your agent's MCP setup guide). The
files stay yours; there's no lock-in.

### 2. Launch on Nodal (hosted) — low-cost, ~2 minutes, no database connection
The fastest way to share with the whole team. **No warehouse/database connection
required** — Nodal serves this context repo, not your data. In short: subscribe, 
add this repo and your dbt repo in the Nodal admin, and share the
endpoint — your team adds it in their own agent and asks questions in plain language.
You get multi-user auth, simple evaluations, and usage logging out
of the box. The Nodal admin also lets **non-technical users edit this context repo**
and open pull requests into it, so your team can evaluate proposed changes both
quantitatively and qualitatively before they merge.

Follow the current subscribe link, pricing, and endpoint in the
**[hosted setup guide](https://docs.nodaldata.io/mcp/share-with-your-team)**.

### 3. Run it in your own cloud/VPC — regulated / enterprise
For data-residency or security requirements, Nodal can build and maintain the MCP server
**inside your environment**. Contact sales: info@nodaldata.io.

## Local checks and the managed learning loop

The open package includes one-shot coverage reports, resumable observed-demand
review, notebook-to-method verification, approved-query regression and drift
review proposals. These work without a hosted service, using customer execution
and model access where required. A missing key or executor is an explicit gap;
local runs never imply continuous monitoring.

As self-service usage grows, managed operation adds team-wide collection,
scheduling and history across these checks:

- **Observability** — what data questions are your business team, marketing team, and
  analysts actually asking, and where is the context thin?
- **Coverage evaluations** — sophisticated evals with coverage metrics that highlight
  when questions are being asked with minimal context coverage, so you evolve the
  context over time in a safe manner.
- **Regression tests** — confidence that questions answered correctly yesterday are
  still answered correctly today, as you add and change context while the business
  evolves.
- **dbt-repo sync** — changes in your dbt models propagate into the affected definitions
  as drafts for your analyst to confirm, so context tracks the warehouse automatically.

This is the gold standard for data teams maintaining context at scale. Contact sales for
a demo, requirements, and pricing: info@nodaldata.io.

---

The files stay open and **self-hosting is always free**. The hosted and enterprise
options are conveniences for team-scale distribution and maintenance — not a lock on the
format. See the full free/paid line on
[docs.nodaldata.io](https://docs.nodaldata.io/enterprise/overview).
