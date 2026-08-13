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

**Default binding setup** (dedicated profile; visible navigation is the product
posture — the user watches the agent read their dashboard):

```json
{"mcpServers": {"chrome-devtools": {"command": "npx",
  "args": ["-y", "chrome-devtools-mcp@1.7.0", "--channel=stable",
           "--user-data-dir=/absolute/path/to/.nodal-dashboard-verify-profile"]}}}
```

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
