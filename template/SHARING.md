# Share this context with your team

This repo is Markdown + YAML that **[company] owns**. A single analyst can point their
own agent at these files and get governed answers for **free** — clone it, read it
locally, done. To put the same context in front of the *whole team* — so a non-technical
business user asks a question in their own agent and gets the answer the analyst would
give — serve it over **MCP** (Model Context Protocol).

## What an MCP server exposes

**Context connector** — this repo as agent tools:
- `get_business_context()` — index of domains, entities, and terminology (call first)
- `search_business_context(pattern, file_filter?)` — regex across the files
- `read_business_context_file(path)` — fetch one file (e.g. `domains/<domain>/reference.md`)
- `list_business_context_files(path?)` — browse the tree

Plus governed answering: retrieve the right definitions and canonical queries, answer
when confident, **escalate to your analyst when not** — then learn from the verified
answer so the next identical question is instant.

**Lineage connector (optional)** — your dbt/warehouse lineage the same way
(`get_dbt_context`, `search_dbt_code`, `read_dbt_file`, `list_dbt_files`). The context
connector says *what a term means*; the lineage connector says *how it's computed*.

## Three ways to serve it

### 1. Build your own — self-host, free
These are read-only file/grep tools over this repo — a small MCP server. Start from the
MCP docs at https://modelcontextprotocol.io (plus your agent's MCP setup guide). The
files stay yours; there's no lock-in.

### 2. Launch on Nodal (hosted) — low-cost, ~2 minutes, no database connection
The fastest way to share with the whole team. **No warehouse/database connection
required** — Nodal serves this context repo, not your data.

1. **Subscribe** →
   <!-- Stripe TEST link (accepts Stripe test cards only, e.g. 4242 4242 4242 4242 —
        not real payment) for the private testing phase. Swap to the PRODUCTION Payment
        Link before onboarding a real paying customer. -->
   https://buy.stripe.com/test_3cI4gB3NB6CbgIb3s2fQI00 — **$50/mo** for the first user,
   **$5/mo** for each additional user.
2. **Create a read-only GitHub access token** scoped to this repo and paste it into the
   Nodal admin at https://aiden.nodaldata.io as your business-context source.
3. **Share the endpoint** — your team adds `https://analyst.nodaldata.io/mcp` in their
   own agent and asks questions in plain language.

You get multi-user auth, analyst **escalation + learning loop**, and usage logging out of
the box.

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
format. See the full free/paid line in the
[project README](https://github.com/nodal-data/nodal-context#the-free--paid-line-explicitly).
