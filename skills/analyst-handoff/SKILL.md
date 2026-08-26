---
name: analyst-handoff
description: Capture analytics knowledge from an analyst who is changing roles, leaving, or transferring domain ownership, producing governed ACF context and eval seeds through context-interview. Use only for an intentional knowledge-transfer or analyst-transition request.
---

# Analyst Handoff

Run a time-bounded, transition-focused form of `context-interview`. The departing
analyst's knowledge must become reviewable context and ground-truth examples, not
a transcript that another analyst has to rediscover later.

## Dependency and ownership

Use the sibling `context-interview` skill for repository discovery/scaffolding,
the confirmation ladder, ACF authoring, eval-seed harvesting, live verification,
and validation. If that skill is unavailable, stop and ask the user to install the
complete Nodal Analytics package; do not invent a second ACF workflow.

The human remains the owner of every confirmed definition. Warehouse and dashboard
access remain read-only. Never request or handle credentials.

## Handoff overlay

1. Establish the transition date, available session time, domains being handed
   off, current owner, and intended successor or escalation role. Do not infer a
   company or person's identity from schema names.
2. Locate or create the context repo through `context-interview`, then read its
   current domain roster and open drafts. Prefer finishing high-risk existing
   drafts before opening low-value new domains.
3. For each domain, apply the prompts in `references/handoff-checklist.md` through
   the normal selection/confirmation ladder. Work in batches of one to three and
   show progress.
4. Every confirmed disambiguation emits an eval seed. Record rejected credible
   readings as negative examples. Unconfirmed recollections remain drafts with a
   named follow-up owner or role.
5. Run the normal per-domain live verification where time and tools allow. A
   missing connection degrades to semantic capture; it never turns recollection
   into verified truth.
6. Validate the context repo and finish with a handoff coverage report.

## Coverage report

Report by domain:

- confirmed definitions and eval seeds added;
- remaining drafts and why they are unresolved;
- dashboards/reports and operational deadlines;
- known wrong approaches and data-quality traps;
- successor or escalation owner;
- verification completed, unavailable, or still required.

Do not claim the handoff is complete while a load-bearing domain has no successor,
contains unresolved contested definitions, or lacks a clearly named follow-up.
