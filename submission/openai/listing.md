# OpenAI Plugin Submission: Nodal Analytics

Use this document as the source of truth when completing the OpenAI plugin
submission portal. Submit the package as **Skills only**. The open-source plugin
does not bundle or operate an MCP server.

Build the upload archive from the repository root:

```bash
python3 scripts/build_openai_submission.py
```

The archive is written to `dist/` and intentionally untracked. The builder
preserves the canonical cross-host skills while normalizing the Claude-specific
`disable-model-invocation` frontmatter in the upload copy. OpenAI's
`agents/openai.yaml` continues to require explicit invocation of `setup-nodal`.

## Listing

| Field | Value |
| --- | --- |
| Plugin name | Nodal Analytics |
| Publisher | Nodal Data |
| Short description | Governed analytics planning and context |
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

Initial public submission of Nodal Analytics 1.5.4. This skills-only plugin
packages seven workflows for setup, analyst interviews and handoffs, governed
analytics planning, dashboard verification, result verification, and independent
challenge review. It does not bundle an MCP server, collect telemetry, transmit
data to Nodal Data, or handle credentials.

## Publisher-only portal steps

- Verify the Nodal Data business identity in the publishing OpenAI organization.
- Confirm the submitter has **Apps Management: Write**.
- Review the privacy notice and terms with counsel or another authorized owner.
- Confirm country and region availability.
- Complete the policy attestations and submit the draft for review.
