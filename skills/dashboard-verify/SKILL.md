---
name: dashboard-verify
description: Verify answers against a named BI dashboard in the user's local browser, capturing widget values and active filters with extraction tiers. Use for dashboard checks and context-interview Stage 5. Not for general browsing, credentials, or warehouse queries.
---

# Dashboard Verify

Extract what a BI dashboard actually shows — values *and* the filter state that
makes those values mean something — into capture files another process (or a
human) can reconcile against. The analyst's browser does the showing; you do the
reading; the analyst stays the authority on what counts as truth.

Look for the nearest `.nodal.local.json` upward to the current git root and accept
only version 1. Treat its browser binding and capability timestamps as hints:
discover the live tools again before use. Missing, invalid, or stale config
degrades to binding discovery below. Never write configuration; only the
explicitly invoked `setup-nodal` skill may do so.

## Hard fences (non-negotiable)

- **Local browser only.** You attach to a browser on the user's machine via an MCP
  binding (`references/browser-contract.md`). Never a hosted/remote browser.
- **Zero credentials.** If a login wall appears, hand control to the user: *"Please
  log in — I'll continue when the dashboard is visible."* Wait on an explicit
  completion condition (URL match / selector visible / cookie present — see the
  contract doc). Never type, store, request, or even look at a credential; never
  bypass a CAPTCHA or SSO prompt.
- **Not a browser agent.** The workflow is exactly: navigate to the named dashboard
  → enumerate widgets → capture filter state → extract values → emit captures.
  No browsing beyond the dashboard's own pages, no clicking around "to explore",
  no other sites.
- **Never fake precision.** Every value carries the `extraction_tier` it came from
  (`references/capture-format.md`). A value read from a screenshot is labeled as
  such; a display-rounded tile ("$3.7K") is recorded as display precision, not
  invented decimals. When a tool bottoms out at vision tier, say so — downgrading
  confidence visibly is correct behavior, not failure.

## Extraction hierarchy — read data, not pixels

Prefer, in order (tag every value with the tier that produced it):

1. **Network payloads** — the BI frontend fetches widget data as JSON; capture the
   response bodies. Exact numbers.
2. *(1.5)* **Embedded data** — figure/config JSON already present in the page
   (e.g. Plotly's `.data`), read via evaluate-js. Exact numbers, no network needed.
3. *(2)* **DOM / accessibility tree** — KPI tiles, tables, SVG charts, aria labels.
   Exact for integers; display precision for formatted values.
4. *(3)* **Export clicks** — per-widget "download CSV". Slow but ground truth.
5. *(4)* **Vision on screenshots** — last resort, canvas-only charts. Use vision to
   *locate* (find the widget, read the filter bar), not to *read* values, wherever
   avoidable.

**Filter-state capture is mandatory, not optional.** A number without its active
filters, date grain, and window anchor is meaningless — and mismatched filters are
the single most common reason a dashboard and a query disagree. Capture it even
when nobody asked.

## The flow

1. **Resolve the target.** A dashboard name + URL from the caller, from the context
   repo's `domains/*/domain.yaml` `dashboards:` entry, or by asking the user for
   the URL. One dashboard per run. If a saved URL, landing page, or bounded
   dashboard-catalog lookup does not reveal the named dashboard, stop searching
   and use the target-not-found recovery in `references/browser-contract.md`:
   ask the user to open that exact dashboard in the connected, already signed-in
   local browser and paste its normal address-bar URL, then navigate directly to
   it and retry once. Never ask for credentials or a tokenized share link.
2. **Attach the browser** per `references/browser-contract.md`. If no browser
   binding is discoverable, run that doc's no-binding preflight (offer explicit
   `setup-nodal` configuration + restart) instead of failing. If the page lands
   on a login wall, do the credential handoff (fences above). If the direct-URL
   retry still cannot reach the named dashboard, report it as unavailable and,
   when called from context-interview Stage 5, return control for a human read;
   do not resume exploratory browsing or repeat the URL request.
3. **Playbook check.** If the context repo has a learned playbook for this
   dashboard (`evals/playbooks/<dashboard-slug>.md`), replay its `replay:` steps
   deterministically. Only when there is no playbook — or a replay step's `expect`
   fails — work agentically, guided by the shipped per-tool playbook
   (`references/playbooks/<tool>.md`); then write/update the learned playbook so
   next time is a replay. Replay is the norm; the model is for first encounters
   and drift (`references/playbook-format.md`).
4. **Enumerate widgets, capture filter state, extract values** per the hierarchy
   above and the tool playbook.
5. **Emit captures** (`references/capture-format.md`), one file per dashboard:
   - in a context repo: `evals/captures/<UTC timestamp>/<dashboard-slug>.capture.json`
     (generated artifact, gitignored like `evals/runs/`);
   - standalone: `./dashboard-verify-captures/<UTC timestamp>/`.
   Report back a compact table: widget · value · tier · filter state. If invoked
   from context-interview Stage 5, return the capture path(s) — the interview owns
   the analyst's blessing; you never mint seeds yourself.
6. **Reconcile (optional).** When the caller also hands you answers to check —
   Stage 5's context-on results, or warehouse numbers the user provides — produce
   the per-value diff per `references/reconcile.md`: windows compared before
   values, tolerance honest about display rounding, report rendered in-session
   and written next to the capture as `reconciliation.md`. Without answers to
   compare, stop at step 5 — never query a warehouse from this skill.

## Reference files (load per step, not all up front)

- `references/browser-contract.md` — the 7 abstract verbs, bindings, completion
  conditions. Load at step 2.
- `references/playbook-format.md` — playbook anatomy, replay semantics, drift
  protocol. Load at step 3.
- `references/playbooks/<tool>.md` — per-BI-tool knowledge (currently: `plotly.md`).
  Load when the tool is identified.
- `references/capture-format.md` — the capture file shape. Load at step 5.
- `references/reconcile.md` — the capture-vs-answers diff and report. Load only
  at step 6, when there are answers to compare.
