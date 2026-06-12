# CLAUDE.md

Authoring rules for agents editing this repo. It contains only Markdown and YAML.

## Do Not
- **No statistics in context.** Qualitative business logic only. Not "~37% of
  sessions" — that belongs in the warehouse.
- **No schema duplication.** Column types live in dbt/Snowflake.
- **No invented definitions.** Leave `_To be confirmed by [owner]._` and
  `status: draft` rather than guessing. Wrong context is worse than missing context.
- **No executable SQL.** Describe patterns in `reference.md`; don't paste runnable
  queries.

## Conventions
- YAML entities/metrics carry `status: draft|confirmed` and a `lineage:` pointer.
- `reference.md` is written for retrieval by an agent (routing triggers, grain,
  gotchas), not as narrative — narrative goes in `context.md`.
- Add `# REVIEW: [question]` where domain-owner verification is needed.
