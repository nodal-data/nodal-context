# Capture format — schema by example

A capture is a generated artifact (like `evals/runs/` traces): gitignored in a
context repo, never committed, never human-authored. This page IS the format
definition — deliberately an annotated example plus field rules, not a JSON
Schema. Formalize it only if (a) a second BI tool proves the shape is truly
tool-agnostic, then inside this skill's references; or (b) captures become a
graded eval-harness input, then as a harness contract next to the NCR — never in
`schemas/` (that directory ships into every context repo and is CI-validated
authored context; captures are neither).

## Annotated example (real, from the Shorelane spike)

```jsonc
{
  // Where and what — enough to re-run the capture
  "dashboard_url": "https://shorelane-data.github.io/shorelane/business/",
  "tool": "plotly-static",            // shipped-playbook id: plotly-static | plotly-dash | <tool>…
  "binding": "chrome-devtools-mcp@1.7.0",
  "captured_at": "2026-08-12T17:54:03Z",   // UTC, ISO-8601 — this becomes a seed's as_of candidate

  // MANDATORY. A value without filter state is not a capture.
  "filter_state": {
    "period": "Last 12 Months",       // every control the dashboard exposes, by label
    "window": "2025-07-01 .. 2026-06-30",  // the RESOLVED window — labels lie, windows don't
    "as_of": "2026-07-24",            // the dashboard's own data-freshness anchor, NOT today
    "date_grain": "month"
  },

  "widgets": [
    {
      "title": "Revenue (Recognized · GAAP)",
      "values": [
        {
          "measure": "recognized_revenue",
          "display": "$5.87M",        // exactly what the screen shows
          "value": 5868799.12,        // exact number IF a tier ≤1.5 source provided it
          "extraction_tier": 2,       // 1 | 1.5 | 2 | 3 | 4  (see table below)
          "precision": "display-rounded"   // "exact" | "display-rounded"
        }
      ],
      "generating_query": null        // SQL if the tool exposes it (rare); else null
    }
  ],

  "extraction_notes": "free text: anything the next run or the reconciler should know"
}
```

## Field rules

- `filter_state` is required even when empty of controls — then it records the
  page's fixed window and `as_of`. The resolved `window` matters more than the
  control labels: the spike found two surfaces sharing a period label ("Last 12
  Months") with different window anchors (build-date vs data-end).
- `as_of` is the dashboard's own freshness stamp (title, footer, metadata), never
  the capture date. `captured_at` is the capture date.
- Every entry in `values[]` has `extraction_tier`; `value` (exact) may be absent
  when only a display string was extractable — never back-fill it by parsing the
  display string as if it were exact.
- One capture file per dashboard per run:
  `evals/captures/<UTC ts>/<dashboard-slug>.capture.json` in a context repo, or
  `./dashboard-verify-captures/<UTC ts>/` standalone.

## Extraction tiers

| Tier | Source | Precision |
|---|---|---|
| 1 | Network response bodies (passive capture or active XHR replay) | exact |
| 1.5 | Data embedded in the page (e.g. Plotly figure JSON) via evaluate-js | exact |
| 2 | DOM / accessibility tree (tiles, tables, SVG, aria) | exact for integers; display otherwise |
| 3 | Per-widget CSV/data export | exact (slow) |
| 4 | Vision on a screenshot | approximate — flag it, never present as exact |
