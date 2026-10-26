---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
How much revenue did we make in June 2026? Please help me plan the analysis.

Here is the available context from our ACF 0.3 repository. These are excerpts;
there is no accessible warehouse connection in this session.

All five confirmed definitions live in separate files under
`domains/revenue/metrics/`. Each sums `amount` in `fct_revenue`, uses
`activity_date`, and belongs to the mutual `revenue` family with discriminator
`measure_name`. Each requires exactly its own discriminator value. The table
contains multiple representations of the same economic activity.

| Metric/file stem | Meaning | Required measure_name |
| --- | --- | --- |
| recognized_revenue | Accounting revenue as performance obligations are satisfied | recognized_revenue |
| billed_revenue | Amount invoiced to customers | billed_revenue |
| collected_cash | Cash received from customers | collected_cash |
| gross_sales | Sales before refunds and discounts | gross_sales |
| net_sales | Sales after refunds and discounts | net_sales |

`company/terminology.md` says that teams use the word "revenue" for all five.
Each metric lists that alias and points to the other siblings. There is no
confirmed company default. All five definitions have human approval metadata.
June means the calendar month June 1–30, in UTC. No other preference or intended
business use has been provided.
