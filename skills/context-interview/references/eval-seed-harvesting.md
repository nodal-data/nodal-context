# Eval-Seed Harvesting

The interview's second output. Every time the analyst confirms a disambiguation, a
metric definition, or a caveat, you write a **seed**: a labeled ground-truth pair
that the eval harness later uses to measure whether the context actually helped.

This is the mechanism that makes the free interview funnel into the paid
measurement: the act of building context *is* the act of labeling ground truth.
Don't skip it, and don't batch it to the end — capture the seed at the moment of
confirmation, while the analyst's exact phrasing is in front of you.

## What a seed is

A seed pairs **a question a user might actually ask** with **the confirmed correct
handling**. The gap between the naive reading of the question and the confirmed
intent is exactly what the agent gets wrong without context.

```yaml
# evals/seeds/collection-rate.seed.yaml
question: "What's our collection rate for Cigna last quarter?"
domain: session-financials
intent: >
  Collection rate = collected / billed on adjudicated claims. "Cigna" is
  state-specific — must resolve to Cigna-TX vs Cigna-FL, not aggregate across
  them. Exclude sessions <45 days old (claims not yet adjudicated). Exclude BHPN.
ir:                          # optional structured decomposition (schemas/ir.schema.json)
  metric: collection_rate    # name in domains/<domain>/metrics.yaml
  dimensions: [payer_name]
  filters:
    - field: payer_name
      op: ilike
      value: "Cigna%"
  time_window: last_quarter  # relative — evergreen seeds never pin a date here
expected:
  kind: sql_shape          # semantic_entity | sql_shape | value_at_snapshot
  must_include:
    - "session age cutoff >= 45 days"
    - "state-specific payer (no cross-state Cigna aggregation)"
  must_exclude:
    - "BHPN / BHPN-CA payers"
provenance: interview        # interview | dashboard | correction
status: confirmed            # confirmed | draft
lineage:
  - source: dbt_core
    models: [fct_session_financials]
```

## The three `expected.kind` types — pick the most robust available

Anchor ground truth so it can't drift as the underlying numbers move. In
descending order of robustness:

1. **`semantic_entity`** — the question maps to a defined metric/entity. Grade:
   did the agent resolve to the right governed entity? Most robust; never goes
   stale. Use whenever a semantic layer or a confirmed metric exists.
2. **`sql_shape`** — grade the agent's *query* for required filters/joins/grain
   (`must_include` / `must_exclude`), not its number. Stale-proof. Use for caveats
   and disambiguations — most interview seeds are this kind.
3. **`value_at_snapshot`** — pin the expected number to a fixed snapshot date.
   Strongest signal, but goes stale unless pinned. Use for dashboard-derived seeds
   where the blessed dashboard gives a known answer as of a date.

**Avoid grading a live number with no snapshot** — it'll fail the moment the data
moves and tell you nothing.

## The `ir:` block — structure, not just phrasing

Populate `ir:` whenever the question decomposes to a metric defined in the
domain's `metrics.yaml` — which is most `sql_shape` and `value_at_snapshot`
seeds. Record the decomposition the confirmed handling implies: `metric`,
`dimensions`, `filters` (same `{field, op, value}` shape as a metric expression's
`mandatory_filters`), and `time_window` (relative tokens like `last_quarter` for
evergreen seeds; absolute `{start, end}` only on `value_at_snapshot`, where
`expected.as_of` already pins the date). Entity-only seeds (`semantic_entity`
with no metric in play) may omit it. The IR is what makes coverage computable
and lets the seed double as the routing contract — it complements `intent` and
`expected`, never replaces them.

## Where "perfect" comes from (this is the design crux)

The on-vs-perfect delta needs a trustworthy "perfect." It comes from exactly two
sources, both human-anchored:

- **Interview-confirmed seeds** (`provenance: interview`, `status: confirmed`) —
  the analyst said "yes, that's the right handling."
- **Blessed-dashboard seeds** (`provenance: dashboard`) — a dashboard the org
  already trusts gives a known answer as of a snapshot date. Stage 5 live
  verification (`live-verification.md`) produces these by answering live and having
  the analyst confirm the number; on a match it also writes the blessed read-only
  SQL to a gitignored sidecar (`evals/verified/<name>.sql`, pointed to by the seed's
  `verified_query_file`) — the reusable answer key, kept local so stale SQL is never
  committed or cloneable. On a mismatch it instead writes a `provenance: correction`
  seed and folds the reason into the domain's `reference.md` / `known-issues.md`.

`status: draft` seeds (drafted from auto-extraction, not yet confirmed) are
**excluded** from the perfect baseline. That's the firewall that keeps
auto-generated guesses from silently corrupting the measurement.

## Long-tail seeds (optional, after the obvious ones)

Once the obvious dashboard/disambiguation seeds exist, you can generate plausible
long-tail questions across the domain from the `reference.md` + `metrics.yaml`, the
way Anthropic generates long-tail evals from business context. Mark these
`provenance: generated` and `status: draft` until a human confirms — they widen
coverage but are not ground truth until confirmed.

## Volume guidance

Don't over-produce. A few dozen confirmed seeds per domain is plenty; accuracy of
the delta saturates well before hundreds. Prefer seeds that encode a *caveat* (a
silent-failure mode) over seeds that restate an obvious metric — the caveats are
where context earns its keep, so they're where the delta is most informative.
