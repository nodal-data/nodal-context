# Reconciliation — capture vs. answers

The one-shot comparison: a dashboard capture on one side, SQL-derived answers on
the other, a per-value verdict in between. This is the free, in-session form of
the eval philosophy — the machine diff that replaces "go check this number on
your dashboard." The continuous/scheduled form is the paid product; this file
covers exactly one run.

## Inputs

- A **capture** (`capture-format.md`) — the dashboard side.
- **Answers** — one per metric being checked, each with the value, the SQL that
  produced it (or the metric definition used), and its resolved time window.
  These come from the caller: Stage 5's context-on agents, or any set of
  warehouse numbers the user wants checked.

You never produce the answers yourself in this skill — reconciliation compares
two things handed to you; it does not go query the warehouse.

## Before comparing values, compare windows

The single most common "mismatch" is two correct numbers for two different
windows. For each pair, first check `capture.filter_state.window` (and grain,
and filters) against the answer's window. If they differ, the verdict is not
❌ — it is **window mismatch**, reported in plain language *before* any value
delta: *"the dashboard shows fully-elapsed months through Jul 31; the query
summed through Aug 12."* Only when windows agree does a value delta mean
anything.

## Tolerance

- The **analyst sets it** when one is in the loop ("close enough" is their
  call, never yours). Suggest a default; don't impose one.
- A `display-rounded` dashboard value (tier 2 tile, `"$5.9M"`) can never be
  compared tighter than its rounding: the tolerance floor is half a unit of the
  last displayed digit. Say so in the report rather than manufacturing decimals.
- An `exact` dashboard value (tier ≤ 1.5, or an integer tile) defaults to exact
  match modulo stated rounding.
- Tier-4 (vision) values get a visibly wider band and an explicit low-confidence
  flag — never a silent ✅.

## The report

One row per compared value, most-severe verdict first:

```
| Widget · measure | Dashboard (tier) | Answer | Δ (abs / %) | Verdict |
```

Verdicts: `✅ match (within tolerance)` · `⚠ window mismatch (explain)` ·
`❌ value mismatch (windows agree)` · `❓ low confidence (tier 4 / display
floor)`. Below the table, one plain-language line per non-✅ row — filter-state
explanation first ("your dashboard filters to completed orders; the query
included refunds"), then any residual delta. End with the count:
`n✅ / n⚠ / n❌ / n❓` and the capture's `as_of` + window so the report is
self-describing.

## Where it goes

- Render the table in-session, always.
- Write the same report to `<capture dir>/reconciliation.md` — next to the
  capture it reconciles, gitignored like everything else there. This file
  doubles as the customer-facing sample-report artifact: it's what "the system
  validated itself" looks like on paper, so keep the prose clean enough to copy
  out and send.

## What this file is not

No seed minting, no context edits, no verdicts overriding the analyst — the
caller (Stage 5, or the user) owns what happens next. A ❌ here is a finding to
hand back — either a context gap or a stale dashboard, and both are exactly what
the user wants surfaced — not a failure to hide.
