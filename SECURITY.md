# Security Policy

## Reporting a Vulnerability

We take the security of nodal-context seriously. If you believe you have found a
security vulnerability, please report it privately — **do not open a public
issue.**

**Preferred:** use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
for this repository (Security tab → "Report a vulnerability").

**Alternatively:** email **security@nodaldata.io** with:

- a description of the issue and its potential impact,
- steps to reproduce (proof-of-concept if available),
- affected version, commit, or file paths.

Please give us a reasonable window to investigate and remediate before any public
disclosure.

## Response Expectations

- **Acknowledgement:** within 3 business days.
- **Status update / triage:** within 10 business days.
- We will keep you informed of progress and let you know when a fix has shipped.

## Scope

This repository is the open-source **tooling** — the context format (ACF), the
interview skill, and the eval harness contract. It does not itself process
production data or hold credentials. Note in particular:

- CI workflows read repository **secrets** (`ANTHROPIC_API_KEY`, `DBT_REPO_TOKEN`).
  Reports concerning secret exposure, workflow injection, or fork-PR privilege
  escalation are in scope.
- Please **do not** include real customer data, credentials, or secrets in any
  report or reproduction.

Thank you for helping keep nodal-context and its users safe.
