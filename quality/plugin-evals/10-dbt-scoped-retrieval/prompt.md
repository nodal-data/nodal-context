---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
Plan how to answer “How many new customers did we gain in September 2026?”
This is a supplied-evidence planning exercise: the tool inventory below is a
fixture, not installed tools. Do not call a warehouse or claim a result. Explain
which evidence operations are still needed and give the plan when possible.

The context names customers.new_customers: distinct canonical customers whose
first-ever order falls in [2026-09-01, 2026-10-01), UTC, across all channels.
Its required filter is is_first_order = true. Its lineage is
model.shop.fct_orders at demo.shop.fct_orders. Required ACF definitions, shared
constraints, entity rules and reference prose have been supplied here. For this
fixture only, the runtime reports valid human-reviewed merge and live freshness
for context revision ctx17 and all dependencies; there are no open decisions.
This statement is not evidence about any real repository. I have not approved
an analytical plan.

Available fixture capabilities:
- overview(): all schema and SQL bodies for 32 models; for project-wide requests.
- model(model_id, columns?): works cold; returns complete selected-model SQL,
  descriptions, tests, constraints, direct dependency IDs, revision and warnings.
  Column selection preserves model-level and cross-column tests.
- search(query, limit): returns short model summaries, IDs and relation identities.
- warehouse_metadata(relation): returns column types and documented constraints.
A full argument contract is available for a selected capability. The other 30
models concern suppliers and advertising; none are dependencies of fct_orders.

Already retrieved model.shop.fct_orders at dbt revision dbt42:
SQL joins stg_orders to dim_customers on customer_id = app_db_customer_id;
is_first_order compares order_date to the all-time minimum order_date per
customer. Its order_id is unique, customer_id nonnull, and a model-level test
requires order_date >= customer_created_date (both columns are involved).
Two same-day orders can both be flagged first, so flagged-row counts differ
from customer counts. The customer relation is model.shop.dim_customers.
Its SQL, account exclusions and key tests have not yet been retrieved. Warehouse
metadata for the named fact has not been checked. All other required technical
evidence is supplied. No evidence for these gaps exists elsewhere in the prompt.
