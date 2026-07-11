# AGENTS.md

Machine-readable orientation for AI systems consuming this repository.

## Purpose
This repo is the **business context layer** for [company]'s analytical data. It is
read by agents at query time to provide semantic grounding that schema metadata and
dbt descriptions alone cannot. Built in Analytics Context Format (ACF).

To serve this context to a whole team over MCP, see `SHARING.md`.

## Navigation
1. Read `company/overview.md` and `company/terminology.md`.
2. Identify the domain; read `domains/<domain>/reference.md` (the agent-facing
   retrieval doc — start here for query routing).
3. For entities, check `entities/*.yaml` (cross-domain) then
   `domains/<domain>/entities.yaml` (domain-specific).
4. For metrics, read `domains/<domain>/metrics.yaml` — honor `parameters` and
   `caveats`.

## Answering a data question
Agents without a skill system (Codex, Cursor) should follow these steps directly:
1. Read `company/terminology.md`.
2. Identify the domain; read `domains/<domain>/reference.md` **first**.
3. Honor every `IF … DO NOT …` routing trigger and `caveats`.
4. Read `domains/<domain>/metrics.yaml` parameters before computing a metric;
   resolve ambiguous terms via the entity files in step 3 of Navigation.
5. Issue **read-only** SQL (SELECT only — never DDL/DML) via the warehouse MCP only.
6. If the context is silent on something the answer depends on, say so — do not
   invent a definition. Apply and state any caveat the answer relies on.

## Editing this repo
Adding or correcting context (not answering a question) does **not** require the
Nodal tool repo — any agent can edit this repo directly. It contains only Markdown
and YAML. Full rules are in `AUTHORING.md`; the load-bearing ones:
1. **No statistics, no schema, no executable SQL, no invented definitions.** Numbers
   and column types live in the warehouse/dbt; leave `_To be confirmed by [owner]._`
   and `status: draft` rather than guessing.
2. YAML entities/metrics carry `status: draft|confirmed` and a `lineage:` pointer.
   Only a human owner flips `draft → confirmed`; add `# REVIEW: [question]` where
   verification is needed.
3. If you resolved an ambiguous term or caveat, add an eval seed under
   `evals/seeds/` (copy `_seed-template.yaml`) — capturing context and its ground
   truth is one act.
4. **Validate before you commit:** `python3 .ci/validate.py` from the repo root
   (needs `pip install jsonschema pyyaml`). CI runs the same check on every PR.

For a **brand-new domain** from scratch, the guided `context-interview` skill (run
from a clone of [github.com/nodal-data/nodal-context](https://github.com/nodal-data/nodal-context))
is recommended, not required — it drafts from your dbt models, verifies answers
live, and harvests seeds automatically. See `AUTHORING.md` for that flow.

## Do NOT use this repo for
- Column types / schema (use the warehouse `information_schema`).
- dbt model definitions / lineage (use the dbt project).
- Statistics, row counts, frequencies (use the warehouse).
- Executable SQL.
