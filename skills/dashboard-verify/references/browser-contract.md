# Browser contract — one page

Playbooks are written against seven abstract verbs, not any specific tool. A
*binding* is whatever MCP server (or built-in browser integration) implements
them in the current session. Discover what's available with ToolSearch/tool
listing; map verbs → tools from the table; note the binding in the capture file.

| Verb | chrome-devtools MCP (default; verified 1.7.0) | Playwright MCP | Claude in Chrome (convenience) |
|---|---|---|---|
| navigate | `navigate_page {url}` | `browser_navigate` | `navigate` |
| wait-for-condition | `wait_for {text}` | `browser_wait_for` | poll via `javascript_tool` |
| capture-network | `list_network_requests` → `get_network_request {reqid, responseFilePath}` — **passive response bodies work**; see notes | `browser_network_requests` (metadata; body support varies) | `read_network_requests` — **metadata only**; tier 1 needs ACTIVE replay (fire the XHR via page-context fetch and read the JSON) |
| query-dom / evaluate-js | `evaluate_script {function}` (arrow-fn string) | `browser_evaluate` | `javascript_tool` (REPL semantics, top-level await) |
| click / export | `click` (uid from `take_snapshot`) | `browser_click` (ref from snapshot) | `computer` (coordinate clicks — least reliable; prefer JS/state reads) |
| screenshot | `take_screenshot` | `browser_take_screenshot` | `computer {action: screenshot}` |

**Optional default binding** (dedicated profile; visible navigation is the product
posture — the user watches the agent read their dashboard):

The explicitly invoked `setup-nodal` skill owns a bundled template for this
binding. Installing Nodal does not enable an MCP server automatically:

```json
{"mcpServers": {"chrome-devtools": {"command": "npx",
  "args": ["-y", "chrome-devtools-mcp@1.7.0", "--channel=stable",
           "--user-data-dir=${HOME}/.nodal-dashboard-verify-profile"]}}}
```

`${HOME}` is expanded by Claude Code at server launch (verified), giving a
machine-independent *absolute* profile path. Keep it absolute — chrome-devtools-mcp
passes `--user-data-dir` through unresolved, so a relative path lands wherever
Chrome's cwd happens to be.

**No-binding preflight.** If tool discovery finds *no* browser binding (none of
the tools in the table above), do not fail and do not improvise with Bash. Read
the project browser mode first; for legacy version-1 configurations, infer
`automated` when `binding` is set and `ask_when_needed` otherwise.

1. For `manual`, do not offer browser setup again. Explain that automated reading
   is disabled for this project and continue with the human-read fallback.
2. For `automated`, use `setup-nodal`'s sanitized `mcp-status` check. If the
   configured binding exists in `.mcp.json` but is not live, ask for the required
   **session restart** and one-time project server approval; do not offer to
   install it again. If the binding is absent or broken, offer to invoke
   `setup-nodal` to repair it with explicit consent.
3. For `ask_when_needed`, explain the value and boundaries once: Nodal can open a
   visible, dedicated Chrome profile to read the named dashboard, capture values
   and active filters, and compare them with warehouse answers; the user signs in
   and Nodal never requests or handles credentials. Offer to invoke `setup-nodal`
   for automated verification or save manual verification for the project. The
   user's selection is an explicit invocation of targeted browser setup; preserve
   the other valid project configuration and save the choice before continuing.
4. Never overwrite an existing binding. If the user prefers Playwright MCP or
   Claude in Chrome, use whichever binding their session already has — the verbs
   table covers all three.

When called from context-interview Stage 5, report "no binding" back to the
interview instead of blocking: it falls back to the human read for this session
and can offer the setup for next time.

**Target-not-found recovery.** A stale saved URL, a landing page that does not
contain the named dashboard, or one bounded catalog lookup with no match is not
a reason to browse more widely. Ask once:

> I couldn't find `<dashboard>` from the saved target. Please open that exact
> dashboard in the connected browser, make sure you're signed in, and paste its
> normal address-bar URL (not credentials or a tokenized share link). I'll retry
> it directly.

Navigate to the supplied URL and retry once. If it reaches a login wall, use the
skill's login handoff and one of the concrete completion conditions below; the
URL is not a substitute for an authenticated browser session. If the named
dashboard is still not visible, report it as unavailable and return to the caller
(Stage 5 falls back to a human read). Do not search other sites, ask for
credentials, or loop on more URLs.

chrome-devtools notes (learned live): `--user-data-dir` and `--isolated` are
**mutually exclusive** — passing both (even `--isolated=false`) makes the server
exit at startup, which the client reports as a cryptic `-32000` connect failure;
network tracking starts at navigation — no pre-arming needed;
`get_network_request` file dumps are sandboxed to the client's declared workspace
`roots` (without roots they restrict to the OS temp dir; `--allow-unrestricted-paths`
overrides) and land at `<stem>.network-response`; headless
(`--headless=true --isolated=true`) is for CI/testing only, never the demo.

**Completion conditions** (for the login handoff and any wait): always concrete,
never "watch and see". Grammar:

- `url_match: <substring or regex>` — e.g. post-SSO redirect back to `/dashboard/`
- `selector_visible: <css selector>` — e.g. `.js-plotly-plot`, `.kpi-value`
- `cookie_present: <name>` — session cookie set after login

A playbook's `completion_condition:` uses one of these three keys. During a login
handoff, poll the condition (wait-for-condition or evaluate-js) at a gentle
interval; tell the user what you're waiting for.

Rule of thumb from the spike: **read state, don't click it** — filter state comes
from DOM/app introspection, not from operating widgets. Clicks are for actions
that ARE the point (export downloads, the user's own login is theirs to do).
If this page needs more than these verbs, the abstraction is failing — fix it
here, don't grow a browser agent in a playbook.
