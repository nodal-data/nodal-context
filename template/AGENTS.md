# AGENTS.md

Machine-readable orientation for AI systems consuming this repository.

## Purpose
This repo is the **business context layer** for [company]'s analytical data. It is
read by agents at query time to provide semantic grounding that schema metadata and
dbt descriptions alone cannot. Built in Analytics Context Format (ACF).

## Navigation
1. Read `company/overview.md` and `company/terminology.md`.
2. Identify the domain; read `domains/<domain>/reference.md` (the agent-facing
   retrieval doc — start here for query routing).
3. For entities, check `entities/*.yaml` (cross-domain) then
   `domains/<domain>/entities.yaml` (domain-specific).
4. For metrics, read `domains/<domain>/metrics.yaml` — honor `parameters` and
   `caveats`.

## Do NOT use this repo for
- Column types / schema (use the warehouse `information_schema`).
- dbt model definitions / lineage (use the dbt project).
- Statistics, row counts, frequencies (use the warehouse).
- Executable SQL.
