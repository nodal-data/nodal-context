# Nodal Analytics agent guide

Use this guide to help a human understand, install, set up, or troubleshoot
Nodal Analytics. It is for onboarding before Nodal's skills are available. Once
the installation is active in a new agent session, hand configuration to the
explicitly invoked `setup-nodal` skill instead of improvising setup behavior.

Canonical product and setup documentation lives in the
[repository README](https://github.com/nodal-data/nodal-context/blob/main/README.md)
and
[getting-started guide](https://github.com/nodal-data/nodal-context/blob/main/docs/getting-started.md).
Verify commands you are unsure about against those files rather than guessing.

## What Nodal is

Nodal is an open-source set of agent skills for building and using governed
analytics context. It helps an analyst and an agent turn warehouse, dbt,
documentation, query-history, and dashboard evidence into human-confirmed
definitions and evaluation seeds. It can then plan analytics questions, verify
results against an approved plan, and challenge disputed answers.

The installed package runs inside the human's existing agent environment. It
does not send data, credentials, queries, results, or telemetry to Nodal. Nodal
does not bundle a warehouse connection, grant itself access, or handle login
credentials. Warehouse and dashboard access remain optional, user-authorized,
and read-only.

## Onboarding rules

Follow these rules throughout onboarding:

1. Inspect first. Identify the agent host, project root, and any existing Nodal
   installation with read-only commands before proposing changes.
2. Install exactly one distribution on a host. A native plugin and project-local
   skills are alternatives; installing both produces duplicate skill discovery.
3. Explain the selected command, files, scope, and restart consequence before
   asking for consent. Run an installation or edit configuration only after the
   human explicitly approves it.
4. Never request, copy, print, or store credentials. Let the host, warehouse,
   browser, or identity provider own authentication.
5. After installing or updating a native plugin, stop at the session boundary.
   Tell the human to start a new agent task before invoking `setup-nodal`; do not
   claim a newly installed skill is live in the current task.
6. Do not write `.nodal.local.json` or `.mcp.json` yourself. In the new task,
   invoke `setup-nodal`, which owns consent, sanitized configuration, capability
   probes, and the optional browser binding.

## Step 1: identify the host and existing installation

State which host you detected and ask the human to correct you if needed. Use
only the matching read-only check:

- Codex: `codex plugin list --json`
- Claude Code: `claude plugin list --json`
- A skills-compatible project: inspect only the project's `.agents/skills/` and
  `.claude/skills/` directories for Nodal skill names.

If `nodal-analytics@nodal` is already enabled, do not reinstall it. Explain that
a new task may be required for the host to discover it. If both a native plugin
and project-local Nodal skills exist, ask which distribution the human wants to
keep; do not remove either without explicit approval.

## Step 2: choose one installation path

Recommend the native plugin for Claude Code or Codex because it keeps the seven
skills together and supports normal plugin updates. Use project-local skills
when the host has no native Nodal plugin support or the human explicitly wants
editable copies in one project.

### Codex native plugin

Explain that this adds the Nodal GitHub repository as the `nodal` marketplace
and enables one local plugin. After consent, run:

```bash
codex plugin marketplace add nodal-data/nodal-context
codex plugin add nodal-analytics@nodal
```

Verify with `codex plugin list --json`. Then ask the human to start a new Codex
task. Do not also run the skills installer.

### Claude Code native plugin

Explain that this adds the Nodal GitHub repository as the `nodal` marketplace
and installs one user-scoped plugin. After consent, run:

```bash
claude plugin marketplace add nodal-data/nodal-context
claude plugin install nodal-analytics@nodal
```

Verify with `claude plugin list --json`. Then ask the human to start a new Claude
Code session. Do not also run the skills installer.

### Project-local skills

Explain that this copies editable skills into the current project and does not
install a native plugin. After consent, run:

```bash
npx skills@latest add nodal-data/nodal-context
```

Select `setup-nodal` and the Nodal workflows the human wants. Restart the host or
start a new task if it does not discover the copied skills immediately. Do not
also install the native plugin on the same host.

## Step 3: hand off to Nodal setup

In the new task or session, ask the human to invoke the installed setup skill:

- Codex: `$setup-nodal Configure Nodal for this analytics project.`
- Claude native plugin: `/nodal-analytics:setup-nodal Configure Nodal for this
  analytics project.`
- Project-local skill: `/setup-nodal Configure Nodal for this analytics
  project.`

Setup discovers candidate context sources, classifies available read-only tools,
and proposes a sanitized project-local configuration for confirmation. It does
not block merely because dbt, query history, documentation, a dashboard, or a
browser binding is unavailable.

Automated dashboard verification is optional. When it would help, `setup-nodal`
can offer a visible, dedicated Chrome profile and merge the bundled project MCP
binding only after separate consent. The human signs in directly; Nodal never
requests or handles credentials. A newly added binding requires another fresh
agent session and one-time project-server approval.

## Common fixes

- **The plugin is listed but the skills are missing.** Start a new task or
  session. Native plugin discovery happens at the session boundary.
- **Nodal appears twice.** Both a native plugin and project-local skills are
  installed. Ask which distribution the human wants to keep before removing
  anything.
- **An update is not visible.** Update through the same installation channel,
  verify the installed version, and start a new task.
- **Setup says the browser binding is configured.** Do not offer installation
  again. Restart the agent session and approve the project server once.
- **Warehouse access is unavailable or denied.** Do not ask for credentials or
  broaden permissions. Report the sanitized capability classification and let
  setup continue with reduced evidence or the human's administrator-approved
  next step.
- **The browser shows a login page.** Ask the human to sign in themselves in the
  visible dedicated browser. Never interact with the login form or request a
  tokenized link.

## Finish the onboarding

Summarize:

- the detected host;
- whether Nodal was already present or which single distribution was installed;
- what changed locally;
- whether a new task or session is required; and
- the exact `setup-nodal` invocation to use next.

Do not report setup as complete until a fresh session has loaded the skill and
the human has confirmed the proposed project-local configuration.
