---
name: analytics-plan
description: Plan and answer business analytics questions against read-only data, grounding interpretations in available ACF, KTX, dbt, documentation, and warehouse evidence. Use for metrics, reports, trends, comparisons, or warehouse questions. Do not use to author context, modify data, or write dbt models.
---

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
   the decomposition compatible with the ACF question IR: `metric`, optional
   `dimensions`, `filters`, `grain`, and `time_window`.
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
5. **Check satisfiability.** Confirm that the available schema can produce the
   requested grain and dimensions, and that every join and mandatory filter is
   supported. Missing evidence is an explicit gap, not an invitation to guess.
6. **Create the plan.** Follow `references/plan-format.md`. The artifact must be
   self-contained enough for a fresh session to execute without conversation
   history. It names the interpretation, evidence, source tables, joins, filters,
   grain, aggregation, time boundaries, output, and unresolved decisions.
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
and `status: draft`. Do not write it. `context-interview` owns human-confirmed
context and seed persistence.
