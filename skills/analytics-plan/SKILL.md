---
name: analytics-plan
description: Plan and answer business analytics questions against read-only data, grounding interpretations in available ACF, KTX, dbt, documentation, and warehouse evidence. Use for metrics, reports, trends, comparisons, or warehouse questions. Do not use to author context, modify data, or write dbt models.
---

Approval contract: new and changed context stays on a named working branch and
has no authored approval status. Human-reviewed protected merge grants definition
approval; consult the live authority through the runtime for the exact revision
and freshness. Missing/expired evidence or stale dependencies blocks governed
use. Explicit branch-test mode is proposed context only. Query/notebook result
verification is separate from definition approval; retain source and review
evidence. See the context-interview SPEC approval-through-merge contract.


# Analytics Plan

Turn a business question into a reviewable analytical plan before executing SQL.
The plan is the translation layer, approval surface, and uncertainty container.
Never jump directly from a plausible interpretation to a query.

## Hard boundaries

- Warehouse access is read-only. Use only `SELECT` or the platform's equivalent
  non-mutating metadata operation. Never execute DDL, DML, grants, procedures, or
  exports from this skill.
- Context sources are evidence, not permission. Use only local files in scope and
  MCP tools already available and authorized by the user or their administrator.
- Never ask for, expose, or persist credentials. Never write `.nodal.local.json`;
  only `setup-nodal` owns it.
- Do not silently choose between conflicting governed definitions. Make the
  conflict part of the plan and ask the user to select.
- Do not edit context while answering. When the user resolves a new ambiguity,
  emit an eval-seed candidate and offer a `context-interview` handoff.

## Workflow

1. **Interpret the request.** Extract metric or measure, dimensions, filters,
   population, grain, time window, comparison, and expected output shape. Keep
   the decomposition compatible with ACF 0.3 IR: either `metric` with optional
   `dimensions`, `filters`, `grain`, `time_window`, or `method`, resolved `metrics`,
   bound `parameters`, optional `dimensions` and `time_window`. Resolve each part
   of a compound question separately. Record canonical targets after clarification;
   changing a cohort selector may change the resolved metric set.
2. **Discover context.** Look for the nearest `.nodal.local.json` upward to the
   current git root and accept only version 1. Treat it as a hint; re-check that
   enabled sources and bindings are reachable. If it is absent or invalid, use a
   bounded local search: the project root and its children to depth 3, plus sibling
   directories to depth 3 — never a home-directory crawl. Use only tools already
   loaded. Read
   `references/context-sources.md` for source routing, authority, and conflicts.
3. **Build an evidence ledger.** For each load-bearing claim record the source,
   authority, owner/freshness when present, and whether another source disagrees.
   Retrieve only what the question needs; do not ingest an entire wiki or catalog.
4. **Resolve the question.** Prefer the highest-authority supported reading, but
   surface competing credible readings. Batch all ambiguities the user can answer
   now, with an evidence-backed recommendation for each. Never invent a foil.
   When several governed family members share an alias and no default is confirmed,
   leave the selection open until the user chooses. A labeled side-by-side comparison
   may be offered as another choice; it is not a safe default that bypasses selection.
   Keep this reply to the choices and conditional plan. Do not supply executable SQL
   for any member or comparison before the interpretation and plan are approved.
5. **Check satisfiability.** Confirm that the available schema can produce the
   requested grain and dimensions, and that every join and mandatory filter is
   supported. Missing evidence is an explicit gap, not an invitation to guess.
   For ACF, expand shared fragments and transitive metric references, honor
   effective draft/blocker state, and keep row filters separate from entity-group
   filters. Respect allowed dimensions and explicit zero-denominator policy.
   A deterministic-form target supplies a reviewed procedure/pattern, not a license
   to invent an unsupported expression or executable query.
   If required data is absent, decline the unavailable answer and name the source
   or responsible owner needed to unblock it. Specify the required grain, identifiers,
   attribution/population rules and period alignment before combining new data with
   the available data. Do not invent a connector/table or promise execution before
   access and the revised plan are established. Available components are not a
   substitute for the requested result.
6. **Create the plan.** Follow `references/plan-format.md`. The artifact must be
   self-contained enough for a fresh session to execute without conversation
   history. It names the interpretation, evidence, source tables, joins, filters,
   grain, aggregation, time boundaries, output, and unresolved decisions.
   For methods, include parameter/default choices, selected component metrics,
   decision IDs, explicit overrides/alignment, output disclosures and checks.
   Clarify undeclared time tokens and fiscal boundaries before binding dates.
7. **Measure uncertainty.** Apply `references/uncertainty-rubric.md`. The score is
   a transparent, static v0 heuristic, never a probability of correctness. Apply
   critical escalation gates even when the numeric score is high.
8. **Ask for approval.** Present a compact business-language interpretation plus
   the material assumptions, uncertainty drivers, and escalation advice. Do not
   execute until the user approves or resolves every blocking decision.
9. **Execute faithfully.** Generate SQL from the approved plan and show it. If the
   plan must change, stop, revise it, re-score it, and request approval again.
10. **Return the answer.** Include the result, SQL, applied definitions/caveats,
    evidence provenance, and preliminary confidence. If `verify-result` is
    available, use its review contract for the full post-execution assessment.
    A method may also require read-only Python in an authorized customer executor;
    show the actual implementation and distinguish executed results from proposals.

## ACF matching and evidence limits

Use the shared matcher (`scripts/match_question.py` for an explicitly supplied
IR) when available. Resolve alias/family ambiguity before matching. Structural
normalization preserves typed AND/OR filters, canonical targets, grain and bound
parameter names; it applies defaults and keeps time tokens for execution without
making a different token a different metric identity. Equivalent structure does
not transfer snapshot verification across dates or parameter values.

Always read structured definitions/entities. Add `reference.md` for equivalent
metrics; `context.md` and the relevant method body for new slices, decompositions
or methods; and company overview/terminology for unresolved questions before
escalation. If matching is unavailable, retrieve the relevant evidence explicitly
and do not claim measured coverage. Distinguish definition, slicing and
verification coverage; an unsupported dimension or blocked dependency remains a gap.

Seed expectations, variants and plaintext/encrypted verified SQL are evaluation
answer keys, not generation context. Leave the evaluated seed out of retrieval.
Use matching IDs/IR metadata to locate governed definitions, never copy an answer
key to produce the answer. Any later verification comparison must preserve its
source, filters, parameterization and snapshot limits.

## Optional Nodal query attribution

When a SQL tool advertises `_nodal_user_question`, copy the original substantive
business request verbatim. Carry it through clarification and plan approval;
an acknowledgment such as "yes, continue" never replaces that request. Omit the
field when the original wording is unavailable. Do not reconstruct it from SQL.

When `_nodal_context` is advertised, use its versioned schema. Record the approved
clarified interpretation separately as `analysis_context.effective_question` only
when the schema permits question text. Use analysis, question, and plan IDs and
revisions supplied by the context service or caller; never invent registered IDs
or assert that a reference has been validated. If no IDs are available, omit them.
Keep the plan revision fixed for its executions; a revised plan needs a new revision.
Model/caller-reported approval is not independently attested human approval.

Before delegation, give each child the original request, approved interpretation,
plan revision, and its assigned question references. Multiple queries may serve
one question; a shared query may reference several questions. Preserve separate
assignments for separate questions. Do not use a global "last question" value.

Copy native client session/turn/agent IDs only when supplied by the client
integration in the current scope. Children retain parent lineage and their own
native agent ID when available. Omit uncertain IDs. Never read, upload, or pass
transcripts, transcript paths, working directories, or private reasoning for
attribution. These IDs locate a conversation; they do not grant access to it.

## Degraded paths

- **No context:** plan from warehouse metadata only, mark semantic claims inferred,
  and lower confidence. Ask rather than inventing a business definition.
- **No warehouse:** a documentation-only plan is allowed, but do not fabricate SQL
  artifacts or values. State that execution is blocked.
- **Too vague:** show the currently known domains or measures and ask the smallest
  batch of questions needed to form an IR.
- **User asks for “just SQL”:** provide a compact plan and uncertainty block first;
  approval may be equally compact, but it is still required.

## Eval-seed candidate

When the user selects among contested meanings, include a small candidate with the
original question, selected intent, structured IR, rejected reading, provenance,
and proposed working-branch content. Do not write it. `context-interview` owns human-confirmed
context and seed persistence.
