# AUTHORING.md

Rules for agents **editing** this repo (adding or correcting context). For rules on
**answering data questions** from this repo, see `CLAUDE.md`. This repo contains only
Markdown and YAML.

## Do Not
- **No statistics in context.** Qualitative business logic only. Not "~37% of
  sessions" — that belongs in the warehouse.
- **No schema duplication.** Column types live in dbt/Snowflake.
- **No invented definitions.** Leave `_To be confirmed by [owner]._` and
  `status: draft` rather than guessing. Wrong context is worse than missing context.
- **SQL only as query patterns.** `reference.md` "Common query patterns" may carry
  a few fenced `sql` blocks, only where the exact query form is the hard-won
  knowledge — pattern, not paste: real model/column names, `<placeholders>` for
  parameter values, each led by a `Without this: …` line naming the failure it
  prevents, analyst-confirmed, never mined from query logs. Complete runnable
  queries stay out of context; blessed SQL lives in the gitignored
  `evals/verified/` sidecar.

## Conventions
- YAML entities/metrics carry `status: draft|confirmed` and a `lineage:` pointer.
- `reference.md` is written for retrieval by an agent (routing triggers, grain,
  gotchas), not as narrative — narrative goes in `context.md`.
- Add `# REVIEW: [question]` where domain-owner verification is needed.
