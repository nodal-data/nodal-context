---
name: data-question
description: >
  Answer a data question using this team's analytics context layer (ACF) and the
  warehouse MCP. Use this skill WHENEVER someone asks a business/analytics question
  that should be answered against the warehouse — e.g. "what was our collection rate
  by payer last quarter?", "how many active clients do we have?", "query the
  warehouse for…". It routes through the confirmed context (terminology, per-domain
  reference docs, metric definitions, entity disambiguations, caveats) so the answer
  uses the team's real definitions instead of a guess from raw schema. Do NOT use it
  to add or edit context (re-run context-interview) or to write transformations/dbt.
---

# Answer a data question from this context

You have a question to answer against the warehouse. This repo is the team's
confirmed business context — use it so the answer reflects their real definitions,
not what you'd infer from raw schema. Read context files directly from this repo.

## Steps

1. Read `company/terminology.md` for what the company's terms mean.
2. Identify the domain the question belongs to; read
   `domains/<domain>/reference.md` **first** — it routes the query (canonical table,
   grain, routing triggers).
3. Honor every `IF … DO NOT …` routing trigger and `caveats` you find. These are the
   silent-failure modes a senior analyst would warn about. When a "Common query
   patterns" block matches the question, start your SQL from its form (fill the
   `<placeholders>`; keep its filters and grain handling).
4. Before computing a metric, read `domains/<domain>/metrics.yaml` and honor its
   `parameters` and `caveats`. Resolve ambiguous terms via `entities/*.yaml`
   (cross-domain) then `domains/<domain>/entities.yaml` (domain-specific).
5. Check `evals/seeds/` for the domain — a matching seed may already carry a blessed
   `verified_query` you should reuse.
6. Issue **read-only** SQL (SELECT only — never DDL/DML) via the warehouse MCP server
   only. If no warehouse MCP is reachable, say so and stop — don't fake a number.

## Answering

- If the answer depends on a caveat the context names, **apply it and state it**
  (e.g. "excluding sessions under 45 days, per the collection-rate caveat").
- If the context is silent on something the answer depends on, **say so** and answer
  with the assumption made explicit — do not invent a definition.
- Return the number, the SQL you ran, and the assumptions/caveats you applied.
