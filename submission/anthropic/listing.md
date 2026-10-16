# Anthropic Plugin Directory Submission: Nodal Analytics

Use this document as the source of truth when completing the Claude plugin
directory submission at https://claude.ai/directory/manage. Submit the
repository root as one **Plugin bundle**. The directory reads the listing from
`.claude-plugin/plugin.json` and `README.md`; there is no separate upload
archive. The plugin contains seven skills and does not declare hooks, agents,
commands, or an MCP server. The optional Chrome DevTools browser configuration
in `skills/setup-nodal/assets/` is merged into a user's own configuration only
with consent.

Once listed, the plugin is available from claude.ai in chat, Cowork, and Claude
Code. The full workflow expects a local executor with project files and
user-configured read-only warehouse or dashboard access, so Claude Code and the
desktop Code tab are the primary surfaces.

## Release verification

Run the repository's required checks on the commit you will submit:

```bash
python3 scripts/run_tests.py
python3 scripts/lint_skills.py
python3 .ci/validate.py
python3 scripts/sync_skill_payload.py --check
claude plugin validate . --strict
```

The portal's **Validate** step runs more checks than `claude plugin validate`.
Before you submit, confirm the directory's file rules
(https://claude.com/docs/plugins/pre-submission-checklist) still hold:

- No `.DS_Store`, `Thumbs.db`, `desktop.ini`, or `__MACOSX` entries are tracked.
- No tracked non-image file exceeds 256 KiB, and the repository stays under 512
  files.
- The only symbolic links are the in-repository `.claude/skills/*` discovery
  links. The plugin does not load them, so they should produce a warning, not a
  blocking finding.
- There are no binary files other than PNG images, and no credentials appear
  anywhere in the repository.

## Source step

| Field | Value |
| --- | --- |
| Repository | `nodal-data/nodal-context` |
| Plugin path | *(empty: repository root)* |
| Branch or tag | `main`, or a release tag if releases should be explicit |

A validation result applies to one commit. Re-validate after every push.

## Listing details

The portal reads these fields from the repository. To change one, edit the
source file and re-validate.

| Field | Value | Source |
| --- | --- | --- |
| Name | `nodal-analytics` | `plugin.json` |
| Version | `1.6.2` | `plugin.json` |
| Description | Plan, verify, and challenge analytics with governed, multi-source context and interview-built ground truth. | `plugin.json` |
| Author | Nodal Data | `plugin.json` |
| License | Apache-2.0 | `plugin.json`, `LICENSE` |
| Homepage | https://github.com/nodal-data/nodal-context | `plugin.json` |
| Listing body | Repository README | `README.md` |

## Data handling answers

- **Reads or stores personal data:** The skills read the analytics files,
  warehouse results, and dashboards that the user connects in their own agent
  environment. Those sources may contain personal data. Nodal stores confirmed
  definitions and eval seeds only in the user's own repository, and stores no
  data with Nodal Data.
- **Sends data to services other than declared connectors:** No. The plugin
  sends no data to Nodal Data and contains no telemetry. Optional CI templates
  scaffolded into the user's repository call the Anthropic API only when the
  user configures their own `ANTHROPIC_API_KEY` as a GitHub Actions secret.
- **Retention:** Nodal Data retains nothing. Generated context lives in the
  user's version-controlled repository under the user's control.
- **Intended for people under 18:** No.

## Compliance step

- Contact email: info@nodaldata.io
- Read the [Anthropic Software Directory Terms](https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms)
  and [Policy](https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy)
  before selecting the four acknowledgements.

## Possible reviewer holds

These findings are expected to be **Held for a reviewer**, not blocking. The
security scan expects the README to describe everything the plugin runs, sends,
or fetches, so confirm `README.md` discloses each one before submitting:

- `skills/setup-nodal/assets/chrome-devtools.mcp.json` launches the pinned
  `chrome-devtools-mcp@1.7.0` package through `npx`, but only after the user
  consents to merging it into their own MCP configuration.
- Scaffolded CI templates under `skills/context-interview/payload/` read
  `ANTHROPIC_API_KEY` and `github.token` in the user's GitHub Actions
  environment. They do not run inside Claude.
- The README documents `npx skills@latest add` as an alternative install
  method. The plugin itself never runs that command.

## Review and submit

- **How new versions reach the directory:** GitHub push webhook (default).
  Setting up the webhook requires admin access to the repository.
- **Auto-publish passing versions:** Leave it off for the first release. Turn it
  on after the first approval if `main` is release-ready on every merge.
- Raise `version` in `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`, and
  `plugin.json` with every release. The directory serves the last published
  version until a new one passes.

## Publisher-only portal steps

- Confirm the submitting account is on a paid plan. On Team or Enterprise, the
  submitter must be an Owner or have the **Directory** permission.
- Connect the GitHub account with push access to `nodal-data/nodal-context` in
  the Claude organization you submit from.
- Run **Validate**, resolve every **Blocking** finding, then complete the
  listing, data handling, and compliance steps.
- Before submitting, load the plugin in Claude Code, the desktop Code tab, and
  Cowork. Use the prompts in `../openai/test-cases.md` and record which skills
  work on each surface.
- After approval, select **Publish**. Track status from **Submissions** in the
  developer portal.

See the official [submission guide](https://claude.com/docs/plugins/submit) and
[pre-submission checklist](https://claude.com/docs/plugins/pre-submission-checklist).
