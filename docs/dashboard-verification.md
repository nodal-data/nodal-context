# Dashboard verification and the optional browser connection

Nodal can compare a warehouse answer with the value shown in a trusted BI
dashboard. The browser connection automates that comparison; it is not required
to build analytics context or answer warehouse questions.

## What automated verification does

For one named dashboard, Nodal opens a visible local browser, captures the values
needed for the comparison, and records the active filters, date grain, and time
window. Capturing the filter state is essential: two correct numbers can disagree
when their windows or filters differ.

Nodal prefers exact data already available to the dashboard, such as a network
response or embedded chart data. It labels lower-confidence extraction from
rendered text or screenshots rather than inventing precision. The resulting
capture can be reconciled with a warehouse answer and reviewed by the analyst.

Without automation, the workflow still works. Nodal asks the analyst to read the
dashboard value and filter state, then uses that human-provided evidence for the
same confirmation step.

## What the connection is

The bundled option is Chrome DevTools MCP. Despite its technical name, this is
not the Chrome developer panel. It is a local bridge that lets the agent navigate
and inspect a visible Chrome session. Nodal configures it in the project
`.mcp.json` and gives it a dedicated browser profile at
`~/.nodal-dashboard-verify-profile`.

The dedicated profile keeps the automated session separate from normal browsing.
The first time it reaches a protected dashboard, the user signs in directly in
that visible browser. Nodal never asks for, types, records, or stores credentials,
and it does not request tokenized share links.

Adding the connection requires explicit consent, a new agent session, and the
host's one-time approval for the project server. Installing Nodal alone does not
enable it.

## When Nodal asks

General project setup does not ask for browser access unless a dashboard has been
named or automated dashboard verification has been requested. The project stores
one of three preferences in `.nodal.local.json`:

- `ask_when_needed`: no choice has been made; ask only when dashboard automation
  would help.
- `manual`: use analyst-read dashboard values and do not ask again.
- `automated`: use the named browser binding when it is live.

If an automated binding is already present in `.mcp.json` but not visible to the
current session, Nodal asks for a restart instead of offering another install.
The saved preference is a convenience hint; every workflow still checks the live
tools before using them.

## The consent choice

Before changing browser configuration, setup explains:

> Nodal can optionally open a visible, dedicated Chrome profile to read one named
> dashboard, capture its values and active filters, and compare them with
> warehouse answers. You sign in yourself; Nodal never requests or handles
> credentials. This is not needed to build context or answer warehouse questions.

Choose automated verification to add the project binding, or manual verification
to save the human-read workflow and suppress future setup prompts. Run
`setup-nodal` explicitly if you later want to change that choice.

Choosing manual changes only Nodal's saved preference. It does not remove a
browser server that another project workflow may use.

## Troubleshooting

- **It says a restart is required.** The project binding exists, but agent hosts
  load new MCP servers only when a new session starts. Restart and approve the
  project server once when prompted.
- **The dashboard shows a login page.** Sign in yourself in the visible dedicated
  browser. Nodal waits for the dashboard; it does not interact with the login.
- **The dashboard cannot be found.** Open the exact dashboard in the connected
  browser and provide its normal address-bar URL. Do not provide credentials or a
  tokenized share link.
- **Automation is unavailable.** Continue with manual verification. The analyst
  reads the value, active filters, and freshness date; the context interview does
  not block.
- **You chose manual and changed your mind.** Invoke `setup-nodal` and explicitly
  request automated dashboard verification.
