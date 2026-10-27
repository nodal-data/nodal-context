# Skill behavior evals

These cases exercise actual model behavior with and without the plugin. They are
separate from the offline executable repository tests. All evidence in the new
ACF 0.3 cases is synthetic and supplied in the prompt; no warehouse, notebook,
browser, scaffold script or MCP server is required.

| Cases | Behavior |
| --- | --- |
| 01–04 | Review SQL/results against approved plans and evidence |
| 05 | Should not invoke verification for a semantics-preserving CTE rewrite |
| 06 | Ask for a revenue-family choice instead of inventing a default |
| 07 | Reject wrong cohort/identity/completeness despite equal totals |
| 08 | Block on an open decision despite historic approval and a passing seed |
| 09 | Decline exact CAC without spend and name the evidence needed |

Run the full suite from the repository root:

```bash
claude plugin eval . --eval-dir quality/plugin-evals --ablation with-without --judge-model sonnet --no-publish
```

For the ACF 0.3 cases alone, append `--case '*acf03*'`. Keep `runs: 3` and both
ablation arms even for a pilot; do not override the judge or replace outcome
graders with skill-invocation checks. Existing `tool_used: Skill` graders are
display-only under ablation. Preserve case 05 as a should-not-fire control.

Read per-run answers and grader reasons in the ignored `results/` report after
every rubric change. A launch failure, missing credential, timeout or cost-limit
stop is an incomplete pilot, not a passing behavioral check. Record failures and
fix skill behavior or demonstrated rubric defects; never relax a rubric merely
to manufacture uplift. `--no-publish` keeps the report local. This command starts
real hosted model runs and incurs account usage; offline tests do not do so.
