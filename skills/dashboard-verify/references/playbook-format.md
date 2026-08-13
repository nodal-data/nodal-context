# Playbook format

A playbook is one markdown file with two halves serving the two runtime modes
(the Stagehand pattern: AI for unfamiliar pages, deterministic replay for known
ones — the model is paid for on first encounter and on drift, never on routine runs):

1. **Prose** — what the model reads when working agentically: how this tool's
   dashboards are built, where the data hides, the traps.
2. **A fenced YAML `replay:` block** — cached deterministic steps, executed
   verbatim without model judgment when present.

## Two kinds, two homes

| Kind | Scope | Lives at | Committed? |
|---|---|---|---|
| **Shipped** | a BI tool ("how Plotly dashboards work") | this skill: `references/playbooks/<tool>.md` | yes — maintained with the skill |
| **Learned** | one specific dashboard (URL, widget list, selectors, completion condition) | the context repo: `evals/playbooks/<dashboard-slug>.md` | yes — small, no data values, no secrets; committing is what makes replay durable across sessions and machines |

A learned playbook never contains extracted values (those are captures) or
anything credential-adjacent. It's a recipe, not a result.

## Replay block anatomy

```yaml
replay:
  tool: plotly-dash                 # which shipped playbook's prose applies
  completion_condition:             # exactly one key: url_match | selector_visible | cookie_present
    selector_visible: ".js-plotly-plot"
  steps:
    - step: 1
      action: navigate              # an abstract verb from browser-contract.md
      args: { url: "http://localhost:8050" }
      expect: "page loads; completion condition met"
    - step: 2
      action: capture-network
      args: { url_pattern: "_dash-update-component" }
      expect: "POST response body with figure JSON"
    - step: 3
      action: evaluate-js
      args: { script_ref: "plotly.md#decode" }   # long scripts by reference, short inline
      expect: "widget list with exact values"
```

`action` values are the seven contract verbs only — a step that needs anything
else means the contract, not the playbook, must change.

## Drift protocol

1. Replay each step; check its `expect`.
2. On an `expect` failure: stop replaying, re-engage the model agentically from
   the shipped playbook's prose (the page changed — vendors ship UI updates).
3. After succeeding agentically, **update the learned playbook in place** so the
   next run replays again. Note what drifted in the playbook's prose half.
4. If the same step drifts repeatedly, the recipe is too brittle — prefer state
   reads (network/DOM introspection) over UI operation; see the contract's rule
   of thumb.

## The abstraction rule

Adding support for a new BI tool touches **only** a new
`references/playbooks/<tool>.md`. If it seems to require editing `SKILL.md`,
`browser-contract.md`, or `capture-format.md`, the abstraction has failed — fix
the abstraction once, don't fork the flow per tool.
