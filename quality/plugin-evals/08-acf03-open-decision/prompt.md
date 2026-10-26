---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
Can you plan our June 2026 net-revenue report? The metric file says confirmed and
last month's seed passed, so I expect we can reuse it. Here is the full relevant
context for this request; there is no live warehouse connection.

`domains/revenue/metrics/net_revenue.yaml` has `status: confirmed`,
`approver: fictional-finance-owner`, and `confirmed_at: 2026-05-20`. The proposed
expression subtracts refunds from recognized revenue. The current document also
contains this unresolved decision, added after that approval:

```yaml
open_decisions:
  - id: refund_period
    question: Should a refund reduce revenue in its posting month or restate the original sale month?
    blocks: [metric:revenue.net_revenue]
```

The mandatory date rule cannot be finalized until that question is answered.
`evals/seeds/monthly-net-revenue.seed.yaml` refers to this metric and has historic
approval metadata and a May snapshot. It contains no resolution of refund_period.
The warehouse has both sale dates and refund posting dates; lack of columns is
not the issue. June is an elapsed UTC calendar month. There is no finance decision
recorded elsewhere and I have not chosen either interpretation.
