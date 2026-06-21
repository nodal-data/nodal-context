# CLAUDE.md

This repo is the **business context layer** for Example Healthcare Company's
analytical data, in Analytics Context Format (ACF). When you are run from this
directory, use it to answer data questions accurately — don't write SQL from raw
schema alone.

## Answering a data question

1. Read `company/terminology.md` for what the company's terms mean.
2. Identify the domain the question belongs to; read
   `domains/<domain>/reference.md` **first** — it routes the query.
3. Honor every `IF … DO NOT …` routing trigger and `caveats` you find. These encode
   the silent-failure modes a senior analyst would warn about.
4. Before computing a metric, read `domains/<domain>/metrics.yaml` and honor its
   `parameters` and `caveats`. For ambiguous terms, check `entities/*.yaml`
   (cross-domain) then `domains/<domain>/entities.yaml` (domain-specific).
5. Issue **read-only** SQL (SELECT only — never DDL/DML) via the warehouse MCP
   server only. (No warehouse MCP configured? See `README.md`.)
6. If the context is silent on something the answer depends on, **say so** — do not
   invent a definition. A flagged gap is more useful than a confident wrong answer.

If the answer depends on a caveat the context names, apply it and state it in your
answer (e.g. "excluding sessions under 45 days, per the collection-rate caveat").

## Editing this repo

Adding or correcting context (not answering a question)? Follow `AUTHORING.md`. The
fastest way to add a domain is to re-run the `context-interview` skill.
