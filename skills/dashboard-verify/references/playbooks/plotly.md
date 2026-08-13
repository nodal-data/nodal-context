# Plotly playbook (shipped)

Covers the three ways Plotly dashboards are served. Verified live against the
Shorelane fixture (static, Dash, and hosted variants), 2026-08-12. Verbs are the
browser-contract's. Good news first: **Plotly never needs vision** — figure data
is embedded in the page regardless of renderer, so even canvas/WebGL traces are
tier 1.5.

## Shared: decoding Plotly figure arrays  {#decode}

plotly.py ≥ 6 serializes numeric arrays as `{dtype: 'f8'|'f4'|'i4'|…, bdata:
'<base64>'}`, not plain JSON arrays. Decode in any evaluate-js context:

```js
const decode = o => {
  if (o?.bdata) {
    const bin = atob(o.bdata);
    const b = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) b[i] = bin.charCodeAt(i);
    const T = {f8: Float64Array, f4: Float32Array,
               i1: Int8Array, i2: Int16Array, i4: Int32Array, i8: BigInt64Array,
               u1: Uint8Array, u2: Uint16Array, u4: Uint32Array, u8: BigUint64Array}[o.dtype];
    if (!T) throw new Error(`unknown bdata dtype: ${o.dtype}`);
    return Array.from(new T(b.buffer), Number);   // Number() also converts BigInt
  }
  return Array.isArray(o) ? o : Array.from(o ?? []);
};
```

Use the FULL dtype map above — real pages mix dtypes per trace (`f8` for money,
`i2`/`u1` for small counts), and a partial map fails with the unhelpful
"T is not a constructor".

Trace data lives in `t.y` for cartesian traces but in `t.values` for pie/donut
traces (with labels in `t.labels`) — decode whichever is present:
`decode(t.y ?? t.values)`.

## Variant A — static Plotly HTML (`tool: plotly-static`)

Rendered files (`plotly.offline`, `fig.write_html`) and static-site hosting.

1. navigate → wait-for-condition `selector_visible: ".js-plotly-plot"`.
2. **Widgets + values (tier 1.5)** — evaluate-js over
   `[...document.querySelectorAll('.js-plotly-plot')]`: per plot `p.layout.title
   .text` and `p.data` (traces: `name`, `type`, `x`, `decode(y)`). Renderer
   (`p.querySelector('canvas')` vs `svg`) affects only the *fallback* tier, not
   this path.
3. **KPI tiles (tier 2)** — site-specific markup around the figures (e.g.
   `.kpi-value` with label/definition/delta in the parent block). Display
   precision only — record the display string; exact values come from the figure
   data or stay absent.
4. **Filter state** — static pages still have client-side controls (period
   switchers toggling pre-rendered panels; e.g. `button.pbtn`, active =
   `.pbtn.active`). All panels typically co-exist in the DOM — scope value reads
   to the visible panel (`offsetParent !== null`) or tag all panels by period.
5. **as_of** — parse from the page/figure title or footer ("as of YYYY-MM-DD"),
   never the capture date: static renders are point-in-time.

## Variant B — live Dash app (`tool: plotly-dash`)

1. navigate → same wait as A.
2. **Self-description (tier 1, no vision):** GET `/_dash-layout` — full component
   tree: every control's id, options, and current value (= the filter state);
   GET `/_dash-dependencies` — the callbacks (inputs → outputs) = which controls
   drive which widgets.
3. **Values (tier 1):** Dash fires its initial callback on page load, so a
   passive-capable binding (chrome-devtools MCP) already holds a
   `POST /_dash-update-component` response containing exact figure JSON for every
   output plus KPI children as structured JSON — capture-network on pattern
   `_dash-update-component`. To read a *different* filter setting, fire the
   callback actively via page-context fetch (also the tier-1 path for bindings
   without passive bodies):

   ```
   POST /_dash-update-component
   {output, outputs: [...from /_dash-dependencies],
    inputs: [{id: <control>, property: "value", value: <filter value>}],
    changedPropIds: ["<control>.value"]}
   ```

4. Tier 1.5 (`.js-plotly-plot`[n].data, as in A) works as a cross-check.
5. The callback response usually restates the applied window in prose (a context
   line) — record it into `filter_state.window`.

## Variant C — hosted static (GitHub Pages etc.)

Same as A over https. Check the page's `as_of` freshness stamp — hosted static
sites re-render on a schedule (or fail to; a stale `as_of` is itself a finding
worth reporting).

## Traps (all hit for real)

- **Same period label, different window.** One fixture's static site anchored
  "Last 12 Months" to its build date; its Dash twin anchored to the data's last
  month — a year apart. Reconcile on `filter_state.window`, never on the label.
- **bdata**: forgetting the decode yields `y: {dtype, bdata}` objects that look
  like empty arrays (`Array.isArray` false, `.length` undefined).
- **KPI tiles are display-precision** ("$3.7K" for $3,679.41). Mark
  `precision: display-rounded`; don't parse display strings into fake exactness.
- **Don't operate the filter widgets.** React-Select-style dropdowns ignore
  synthetic events and coordinate clicks are scale-fragile. Read state from
  `/_dash-layout`/DOM; change state via the callback POST (B.3).
