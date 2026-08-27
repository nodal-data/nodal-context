---
name: challenge-result
description: Challenge a completed analytics answer when the user disputes it or requests a second opinion, testing alternative interpretations and failure hypotheses before upholding it, escalating uncertainty, or handing a correction to analytics-plan. Do not use for routine first-pass verification.
---

# Challenge Result

Run a skeptical second-pass review after an analytics answer has already been
planned, executed, and returned. The user's concern is a hypothesis to test, not
proof that the answer is wrong. The absence of a discovered defect is not proof
that the number is correct.

This is not the routine post-query check. `verify-result` checks fidelity to the
approved plan; this skill independently challenges the interpretation, plan,
execution, evidence, and result when the user asks for another take or says the
answer seems wrong.

## Boundaries

- Warehouse access remains read-only. Diagnostic queries must be bounded and
  tied to a named hypothesis. Never run DDL, DML, grants, procedures, or exports.
- Never modify context, configuration, dashboards, the original SQL, or
  warehouse data.
- Never execute a replacement analysis. A material correction returns to
  `analytics-plan` for a revised plan and fresh user approval.
- Use only local files in scope and MCP tools already available and authorized.
  Never request, expose, or persist credentials.
- Do not treat the user's expectation, query history, a typical range, or an
  unmatched dashboard value as ground truth.
- Do not silently make a material assumption to force a preferred answer.

## Intake

Start by distinguishing a specific concern from a general second opinion:

> Are you flagging a specific concern, or would you like an independent second
> review?

If the user has a concern, ask only the smallest useful batch about what they
expected, what differs, the source or business event behind that expectation,
and the decision the answer will inform. Do not require the user to invent a
concern when they only want a second review.

Recover the original question, approved plan, evidence ledger, executed SQL,
result or result metadata, and `verify-result` output from the conversation or
workspace. Ask for a missing artifact only when its absence blocks a material
check. If there was no approved plan, reconstruct the apparent plan from the SQL
and label plan comparison unavailable.

## Review

1. **Reconstruct independently.** Derive the expected interpretation and
   analytical shape from the original question and governed evidence before
   comparing them with the prior conclusion. When an isolated reviewer is
   available, follow the independence protocol in
   `references/challenge-rubric.md`. Otherwise disclose that the reconstruction
   is structured but not context-isolated.
2. **Build hypotheses.** Read `references/challenge-rubric.md` and select the
   material, plausible failure modes supported by the artifacts. Include the
   user's concern without letting it crowd out independent alternatives. Test
   whether the user's expectation could be wrong as well as whether the reported
   number could be wrong.
3. **Keep a challenge ledger.** For each hypothesis record the evidence that
   would distinguish it, checks performed, finding, likely impact, and evidence
   still missing. Missing evidence remains unknown.
4. **Run bounded diagnostics.** Use read-only metadata or aggregate checks only
   when necessary to resolve a named hypothesis. Stop broad exploration when a
   material defect is established, all high-priority hypotheses are resolved, or
   required evidence is unavailable. Record material hypotheses left untested.
5. **Audit assumptions.** Separate assumptions inherited from the original plan,
   new assumptions introduced by the challenge, assumptions contradicted by
   evidence, and assumptions that require human approval.
6. **Reach an outcome.** Apply the outcome rules in the rubric. Reuse the
   existing plan uncertainty and result-review confidence conventions; do not
   invent a third numeric confidence system.
7. **Replan when needed.** For `REPLAN`, hand the challenge evidence and replan
   brief to `analytics-plan`. If it is available, use it to produce the revised
   analytical plan under its normal format and approval gate. If unavailable,
   return only the replan brief and ask the user to install the complete Nodal
   Analytics package. Do not create a competing plan format or execute SQL.

## Output

Lead with exactly one outcome:

- `UPHELD`: no material defect was found in the hypotheses that could be tested;
  never state that the number is proven correct.
- `REPLAN`: a material defect or more credible interpretation was identified and
  a revised plan is required before another execution.
- `INCONCLUSIVE`: a credible concern remains, but available evidence cannot
  resolve it safely.

Then provide:

- the user's concern, or `general second review`;
- the independently reconstructed interpretation;
- original, challenged, and approval-required assumptions;
- the challenge ledger, including untested material hypotheses;
- findings with evidence and likely impact;
- existing uncertainty/confidence and any justified downgrade or evidence-backed
  change;
- escalation target and reason when applicable;
- the next action: none, expert review, or revised-plan approval.

For `REPLAN`, show the exact differences from the original plan and include the
revised `analytics-plan` artifact when available. Never proceed from the revised
plan to execution without explicit approval.

If the user resolves a new semantic ambiguity, emit a draft eval-seed candidate
and offer a `context-interview` handoff. Do not write context or seed files from
this skill.
