---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
Two independent requests for retrieval planning only; no installed connector or
SQL execution is needed. Explain the appropriate next operations for each.

A. I ask for new customers. Search returned model.retail.fct_orders and
model.wholesale.fct_orders, both aliased “orders”. Each has a short summary but
no established mapping to the requested business metric. An authorized scoped
search can return lineage, relation identity and domain evidence. Do not assume
retail is the default. My intended business scope has not been confirmed.

B. I explicitly ask for a project-wide overview of dbt models and their roles.
The connector advertises an overview capability for this purpose, a paginated
compact model index and individual model reads. There is no narrower metric
question hidden in this request. The host already supplies the full contracts
for these tools. I have not requested detailed SQL for every model.
