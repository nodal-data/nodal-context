# OpenAI Plugin Submission: Nodal Analytics

Use this document as the source of truth when completing the OpenAI plugin
submission portal. Submit the package as **Skills only**. The open-source plugin
does not bundle or operate an MCP server. It requires a local executor and should
be listed as **Desktop only**. Installation provides the seven skills; it does
not provision a warehouse connection. Users configure and authenticate their
own approved read-only connection, and setup can proceed with unavailable
connections recorded as such.

Build the upload archive from the repository root:

```bash
python3 scripts/build_openai_submission.py
```

The archive is written to `dist/` and intentionally untracked. The builder
preserves the canonical cross-host skills while normalizing the Claude-specific
`disable-model-invocation` frontmatter in the upload copy. OpenAI's
`agents/openai.yaml` continues to require explicit invocation of `setup-nodal`.

## Release verification

Run the repository's required checks before building the upload archive:

```bash
python3 scripts/run_tests.py
python3 scripts/lint_skills.py
python3 .ci/validate.py
python3 scripts/sync_skill_payload.py --check
python3 scripts/validate_codex_package.py --list-available
claude plugin validate . --strict
```

The direct test runner covers repository and isolated installed-skill scaffold
smoke tests. Also extract the built ZIP into a temporary directory and smoke-test
the packaged scaffold there. Before publication, manually verify desktop setup
both after installation in a fresh chat and when installing during an existing
chat. Confirm setup asks before writing project configuration and explains
missing connections without requesting credentials. These desktop checks are
maintainer-operated; offline checks do not establish that they passed.

## Listing

| Field | Value |
| --- | --- |
| Plugin name | Nodal Analytics |
| Publisher | Nodal Data |
| Short description | Governed analytics workflows |
| Category | Data & Analytics |
| Website | https://nodaldata.io |
| Support | https://github.com/nodal-data/nodal-context/blob/main/docs/support.md |
| Privacy policy | https://github.com/nodal-data/nodal-context/blob/main/docs/privacy.md |
| Terms of service | https://github.com/nodal-data/nodal-context/blob/main/docs/terms.md |
| Logo | `assets/nodal-logo.png` |

### Long description

Build human-owned analytics context through structured interviews, plan
read-only data questions against approved definitions, verify SQL and results,
and challenge disputed answers with an independent review. Nodal keeps
qualitative business logic in version-controlled context, requires a human to
confirm definitions, and creates evaluation seeds from each confirmed
disambiguation. It works with ACF, KTX, dbt, approved documentation, and
user-configured read-only warehouse or dashboard connections. The open-source
plugin runs in the user's agent environment and sends no data or credentials to
Nodal Data.

## Starter prompts

1. Build a governed analytics context layer with me.
2. Plan and answer this analytics question using our approved context.
3. Verify this SQL and result against the approved plan.

## Availability

Select every country or region where OpenAI makes the plugin directory available
and where Nodal Data is prepared to provide the support and legal coverage named
above. The publisher must make the final selection in the portal.

## Initial release notes

Initial public submission of Nodal Analytics 1.6.1. This skills-only plugin
packages seven workflows for setup, analyst interviews and handoffs, governed
analytics planning, dashboard verification, result verification, and independent
challenge review. It does not bundle an MCP server, collect telemetry, transmit
data to Nodal Data, or handle credentials.

## Publisher-only portal steps

- Verify the Nodal Data business identity in the publishing OpenAI organization.
- Confirm the submitter has **Apps Management: Write**.
- Review the privacy notice and terms with counsel or another authorized owner.
- Confirm country and region availability.
- Upload the generated ZIP at https://platform.openai.com/plugins using
  **Skills only**, then resolve required metadata and skill scan findings.
- Confirm the listing is marked **Desktop only** and the setup action invokes
  the packaged `setup-nodal` onboarding skill. If the portal rejects
  `requires_local_executor`, contact OpenAI to confirm organization access.
- Complete the policy attestations and submit the draft for review.
- After approval, select **Publish plugin** when ready. GitHub releases and
  marketplace updates do not automatically publish directory skill updates.

Skills-only submissions do not require the MCP-specific review cases or demo
recording. Keep `test-cases.md` for behavioral verification. See the official
[submission guide](https://developers.openai.com/plugins/deploy/submission) and
[desktop-only guidance](https://developers.openai.com/plugins/deploy/desktop-only).
