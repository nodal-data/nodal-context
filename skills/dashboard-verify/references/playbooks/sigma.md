# Sigma playbook (shipped)

Sigma organizes dashboard content as **workbooks containing pages containing
elements**. Nodal's dashboard-sized unit is one workbook page: one target, one
filter state, one capture file. An organization landing URL is a catalog, not a
dashboard target. Verified live against two multi-page Shorelane workbooks on
2026-09-04; the semantic attributes below are observations, not assumptions
about hashed application CSS.

Use `tool: sigma`. The verbs below are the browser contract's. This playbook uses
the analyst's authenticated local browser only. Never request Sigma API tokens,
inspect credentials, or turn a browser session into a reusable credential.

## Resolve an organization with multiple workbooks {#resolve}

1. If the caller provides a workbook-page URL, navigate to it directly. The
   workbook path has the shape `/workbook/<workbook-name-and-id>`. In the live
   app, selecting a non-default page adds `?:nodeId=<page-id>`; the first page's
   initial URL can omit it. Some embed/API-generated URLs instead use
   `/page/<page-id>`. Preserve the selected workbook and page identifiers even
   when the current address omits the default page id.
2. If the caller provides an organization landing URL, perform one bounded
   catalog read in that organization. Query the visible DOM for workbook links
   and their accessible names. Match the requested workbook name exactly after
   trimming whitespace and case-folding.
3. Require one unique workbook match. Names can repeat across folders, so retain
   the matched link and workbook identifier. If no unique match exists, use the
   browser contract's target-not-found recovery instead of opening candidates.
4. In the workbook, enumerate its visible page tabs and require one unique page
   match. If the request names the whole workbook, treat each visible dashboard
   page as a separate, page-scoped run and capture; do not merge page filters or
   widgets. Hidden pages are out of scope unless the caller names one directly.
5. Store the resolved workbook-page URL in the learned playbook. On replay,
   navigate directly rather than traversing the organization catalog again.

The verified organization home exposed normal anchors whose paths contain
`/workbook/`. De-duplicate repeated anchors by resolved href, not name. The same
visible name can point to several workbook ids (the live catalog contained this
case), which correctly triggers the unique-match guard.

The capture filename should include both workbook and page slugs when a request
produces more than one page-scoped capture, for example
`sales-overview-executive.capture.json`. Workbook identity belongs in
`filter_state` too, because page names such as "Overview" are commonly reused.

## Wait for a stable page {#ready}

A `/workbook/` URL alone is not proof that values are ready. Wait until all of
these are true:

- the requested page tab is selected (prefer `aria-current`, selected-state
  semantics, or a stable test id over CSS classes);
- at least one named workbook element is visible; and
- visible loading, refresh, or query-in-progress indicators have cleared.

Use role, accessible name, and stable `data-testid` attributes discovered from
the current page. Do not ship hashed CSS classes or positional selectors. A
loaded workbook shell with blank tiles fails the readiness check.

Current Sigma markup exposes `layoutCanvasContainer[data-loading="false"]` after
the page layout settles and labels query progressbars `Loading` or `Loaded`.
Require the former, no visible `progressbar` named `Loading`, and a non-empty
element inventory. Do not rely on `workbook-body[data-dashboardloaded]` alone;
live workbooks disagreed on that flag even after their visible values loaded.

## Inventory pages, elements, and identity {#inventory}

Before reading values, use query-dom/evaluate-js to produce:

- organization slug, workbook name and id, page name and id, and the normal
  address-bar URL;
- the selected workbook version (`published`, `draft`, saved view, or tag) when
  the UI exposes it;
- every visible element's title, accessible role, stable element id/test id when
  present, and bounding relationship between its title and value region; and
- every visible workbook/page control with its label and displayed selection.

Scope element queries to the selected, visible page. Sigma can keep inactive or
virtualized content in the DOM; `textContent` from the whole document can mix
pages, off-screen table rows, menus, and stale values. Never identify an element
only by ordinal position.

On the verified surface, use these semantic hooks when present:

- `header-document-menu-button` for the workbook name;
- `page-tab-bar` containing `page-item-<page-id>` children, with the active child
  carrying `data-selected="true"`;
- `element-<element-id>` containers with a `data-sheet-id`, and their local
  `dynamic-title`/`sheet-<title>` descendants; and
- `workbook-body` and `layoutCanvasContainer` only as page-scoped containers and
  readiness signals, not as value sources.

Treat the suffixes and `data-sheet-id` values as opaque identities. Test ids
whose suffix is a title can change when authors rename an element, so the
learned playbook retains both the opaque element id and the current title.

## Extract values by tier

### Tier 1 — passive network response bodies

Start passive network capture before direct navigation or page selection. Sigma
loads workbook metadata separately from element query results. Correlate a value
only when the observed metadata ties the response's workbook, page, and element
identifier to the inventoried element.

Accept structured JSON rows or scalar results as exact. Sigma deployments may
transport results as Arrow, protobuf, compressed, chunked, or otherwise encoded
payloads. Such a body is not exact merely because it came from the network: use
it only if the binding can decode it deterministically and preserve types. Do
not guess private endpoint request shapes, replay mutations, or label opaque
bytes as tier 1.

The public Sigma REST export API requires separate credentials and is not this
path. `dashboard-verify` never requests an API token. Use only responses already
available to the authenticated local page, then fall through when they are not
decodable.

### Tier 2 — DOM and accessibility

Read single-value/KPI displays, table cells, legends, axes, and accessible chart
summaries from the visible element region. Record the exact display string.
Integers with no abbreviation can be exact; currency, percentages, decimals,
and abbreviated values such as `$3.7M` are `display-rounded` unless another tier
provides the underlying number.

KPI element containers currently expose a local `kpi-value` descendant, while
the title is a sibling under the same `element-<element-id>` container. Pair them
inside that container; a document-wide list of all titles followed by all KPI
values is not a reliable mapping.

Visible tables yield only visible rows. Virtualized rows that are absent from the
DOM are not evidence of the full table. Chart tooltips may be read from the DOM
when already exposed, but do not sweep pointer coordinates and pretend the
result is a complete series.

`row-column-count` (for example, "12 rows – 15 columns") is inventory metadata,
not a table value. Likewise, an accessible chart series label without points is
not a captured series. A chart element that says `No data` in the DOM while it
visually renders is evidence that the DOM tier is insufficient, not that the
business result is empty.

### Tier 3 — on-demand element export

When network and DOM reads are insufficient, use the target element's own menu
and an on-demand CSV or JSON download. Anchor the menu operation to the element
title/id from the inventory, verify the dialog names that element, and preserve
the current control state. A one-row KPI export or tabular chart export is exact
when its columns can be mapped unambiguously to the displayed measure.

Only download locally. Never choose scheduled delivery, email, Slack, webhook,
cloud storage, sharing, or permission actions. If the viewer role disables
downloads, record that tier 3 is unavailable and continue to tier 4.

### Tier 4 — screenshot

Use vision only for a canvas-only value that is neither accessible nor
exportable. Crop to the named element, keep its title in-frame, preserve the
display string, and mark the value approximate. Screenshots can locate controls
and elements; they do not prove hidden rows or exact chart points.

## Capture Sigma filter state {#filters}

Record filter state before values and again after extraction; a mismatch means
the capture must be retried. At minimum include:

```jsonc
{
  "workbook": {"name": "Sales Overview", "id": "..."},
  "page": {"name": "Executive", "id": "..."},
  "workbook_version": "published",
  "controls": {
    "Order Date": {"id": "date-control", "display": "Last 12 months"},
    "Region": {"id": "region-control", "display": "All"}
  },
  "window": "2025-09-01 .. 2026-08-31",
  "as_of": "2026-08-31",
  "date_grain": "month"
}
```

Sigma controls can target one element, many elements, data-model parameters, or
synced copies on several pages. Capture every visible control by label and
stable control id when exposed. Also capture visible element-level filters,
saved-view state, URL parameters, and published/draft/tag state. Never assume a
same-named control on another page or workbook has the same targets or value.

Current segmented/list controls expose a `variable-<control-name>` container
inside an ancestor with an opaque `data-node-id`. Their accessibility copy
includes a native `select`; read its `value` and `selectedOptions` without
opening or operating the visual control. Keep the `data-node-id` as identity and
the nearby `dynamic-title` text as label. Do not treat every option in the hidden
select as active—the selected option is the filter state.

Resolve relative date labels to explicit bounds from page metadata, element
context, or a deterministic export. If the bounds or data-freshness anchor are
not exposed, set them to `null` and explain the limitation in
`extraction_notes`; do not substitute `captured_at`. Upstream or inherited
element filters may be invisible to a viewer. When they cannot be recovered from
metadata or export, say filter coverage is partial rather than claiming an
unfiltered result.

## Learned replay recipe

A learned playbook should use the direct workbook-page URL and stable identities
observed during the first run. Its replay normally follows this shape:

```yaml
replay:
  tool: sigma
  completion_condition:
    url_match: "/workbook/<workbook-name-and-id>"
  steps:
    - step: 1
      action: navigate
      args: {url: "<normal workbook-page URL>"}
      expect: "requested workbook and page identifiers match"
    - step: 2
      action: wait-for-condition
      args: {script_ref: "sigma.md#ready"}
      expect: "selected page has named elements and no visible loading state"
    - step: 3
      action: evaluate-js
      args: {script_ref: "sigma.md#inventory"}
      expect: "workbook/page identity, controls, and stable element inventory"
    - step: 4
      action: capture-network
      args: {identity_source: "inventory"}
      expect: "responses correlated by workbook, page, and element id, or explicit fallback"
    - step: 5
      action: evaluate-js
      args: {script_ref: "sigma.md#filters"}
      expect: "filter state unchanged since step 3"
```

Replace placeholders with observed values in the learned playbook. If a stable
selector or response correlation changes, stop replay at that failed expectation
and follow the drift protocol; do not fall back to positional clicks.

## Sigma traps

- **Organization home is not a dashboard.** Resolve one workbook and one page
  before capturing anything.
- **Page-name collisions.** `Overview` in two workbooks is two different targets;
  preserve workbook and page ids.
- **Published versus draft.** Values can differ. Record the selected version and
  never silently switch modes.
- **Synced controls are not global controls.** Record each page's displayed state
  and do not copy values across pages.
- **Lazy and virtualized content.** A blank tile or short DOM table can be a load
  state, not zero rows.
- **Opaque network results.** Encoded bytes are not tier 1 until decoded and tied
  to an element.
- **Dynamic titles.** Keep stable element ids alongside titles; titles can include
  current filter values.
- **Exports can escape the read-only workflow.** Local on-demand download is the
  only permitted export action; never schedule, send, share, or write back.
