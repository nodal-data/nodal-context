# Nodal Analytics Plugin Privacy Notice

**Effective date:** October 26, 2026

This notice describes the open-source Nodal Analytics plugin distributed by
Nodal Data. It does not describe Nodal Data's separate hosted products or
services.

## What the plugin does

The plugin is a package of agent instructions, templates, and local scripts. It
runs in the agent environment chosen by the user. The plugin helps users create
and review analytics context, plan read-only data questions, verify analytical
results, and challenge disputed answers.

## Data collection by Nodal Data

The plugin does not send data to Nodal Data. It contains no Nodal telemetry,
analytics collection, advertising, or tracking code. Nodal Data does not receive
the user's prompts, warehouse schemas, query text, query results, dashboard
captures, generated context, or credentials through this plugin.

Local workflows create or edit files in the user's selected project and temporary
working directories. Customer-configured CI workflows can publish review proposals,
comments and reports to the customer's repository. These files and repository
outputs remain under the customer's control; they are not sent to Nodal Data.

## Agent and third-party processing

The agent host processes information according to the user's agreement with
that host. For example, information supplied to ChatGPT or Codex is processed
under the applicable OpenAI terms and privacy notices.

Users may optionally connect their agent to a warehouse, browser, documentation
source, or other service. Those connections are configured and authenticated by
the user, not by Nodal Data, and are governed by the relevant provider's terms
and privacy practices. The plugin instructs agents to use read-only warehouse
access and never asks users to give credentials to Nodal Data.

Optional model-assisted evaluation, question matching, seed re-grading and semantic
lint send their selected inputs to the configured model provider using the
customer's model access. Depending on the operation, inputs include questions,
authored context, generated analysis and grading evidence. Answer generation
excludes seed answer keys and verified SQL; a separate evaluator may receive
expected values and execution evidence for grading. Semantic lint sends bounded
authored-context comparisons, excluding notebook files, observations, answer keys
and raw execution results. Deterministic validation does not call a model.

Notebook import is static and does not run cells. Explicit notebook verification
uses customer-selected reference, answer and judge executors. The independent
answering agent receives the reviewed method and agreed input bindings, without
the source notebook implementation or reference output. The comparison and judge
use the resulting execution evidence. Executor/model access and the data shared
with those services remain the customer's responsibility and configuration.

Configured GitHub workflows may publish draft drift changes, affected-object
lists and semantic warnings with short context excerpts. Verified-query regression
publishes sanitized seed IDs and status categories, not plaintext SQL or query
results. Local commands do not implicitly publish those reports.

## Retention and deletion

Because the plugin does not transmit information to Nodal Data, Nodal Data does
not retain plugin usage data. Users control and may delete the local files the
plugin creates. Retention by an agent host or an optional third-party connection
is controlled by that provider and the user's configuration.

ACF 0.3 keeps observed questions in ignored `evals/observed/`, and caches,
migration backups, notebook evidence and review journals under ignored `.nodal/`
or `evals/runs/`. Simulated interviews keep private briefs, transcripts, pending
questions and summaries in their selected local clean room. These files may
contain confidential business information. Source notebooks stay in their source
location; the context repo records provenance pointers and, after human review,
approved snapshot expectations.

Verified SQL plaintext is ignored under `evals/verified/`. Customers may commit
encrypted `.sql.age` or `.sql.sops` answer keys; private decryption keys remain in
customer-controlled storage. Explicit local-only mode does not encrypt SQL.
Gitignore rules do not hide files from agent tools, provide encryption or remove
previously committed history. Serve only the authored context allowlist described
in the generated repo's `SHARING.md`, and review Git changes before sharing them.

## Changes and contact

Material changes to this notice will be published in this repository with an
updated effective date. Questions may be sent to
[info@nodaldata.io](mailto:info@nodaldata.io). Security issues should follow the
[security policy](../SECURITY.md).
