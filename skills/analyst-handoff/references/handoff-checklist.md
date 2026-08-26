# Analyst Handoff Checklist

Use these as prompts, not as a questionnaire wall. Select only the sections
relevant to the current domain and ask one to three items at a time.

## Meaning and routing

- Which ordinary business terms have a non-obvious company-specific meaning?
- Which two teams or dashboards disagree, and what evidence supports each reading?
- Which question sounds routine but must be routed to a different table, grain, or
  owner?
- Which default population, exclusion, time window, or timezone is usually left
  unstated?

## Query and data traps

- Which join produces plausible fanout?
- Which status, null, fallback, late-arriving record, or manual adjustment changes
  the answer?
- Which metric is non-additive or uses different dates by measure?
- Which “obvious” query has caused a wrong decision before?

## Operations

- Which dashboards, recurring reports, close processes, or executive numbers does
  this domain support?
- What deadlines, refresh schedules, or manual steps are not encoded in the data?
- Who approves changes and who should be contacted when the number looks wrong?

## Open work

- Which investigation, migration, or reconciliation is unfinished?
- Which definitions are recollection rather than verified fact?
- What should the successor validate in their first week?

Each accepted answer must land in the appropriate ACF artifact and, when it
resolves ambiguity, in an eval seed. A transcript alone is not a handoff artifact.
