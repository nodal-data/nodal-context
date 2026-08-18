---
name: dashboard-verify
description: >
  Read a BI dashboard in the analyst's own local browser and extract its widget
  values AND active filter state as tier-tagged capture files — so answers can be
  verified against the dashboard without asking a human to read numbers off a
  screen. Use this skill whenever the user wants to check answers, context, or SQL
  against what a dashboard shows — "validate against my dashboard", "read the
  dashboard", "does this match the dashboard", "self-validate", "extract the
  dashboard values" — and from Stage 5 of the context-interview skill in place of
  asking the analyst what the dashboard says. Works with any MCP browser binding
  (chrome-devtools MCP is the default). It is NOT a general browser agent: it does
  exactly one workflow (navigate to a named dashboard → enumerate widgets → capture
  filter state → extract values → emit captures) and refuses side quests. It never
  handles credentials — the user logs in themselves in their own browser.
---

# Dashboard Verify

Extract what a BI dashboard actually shows — values *and* the filter state that
makes those values mean something — into capture files another process (or a
human) can reconcile against. The analyst's browser does the showing; you do the
reading; the analyst stays the authority on what counts as truth.

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
   the URL. One dashboard per run.
2. **Attach the browser** per `references/browser-contract.md`. If no browser
   binding is discoverable, run that doc's no-binding preflight (offer the
   shipped `.mcp.json` setup + restart) instead of failing. If the page lands
   on a login wall, do the credential handoff (fences above).
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
