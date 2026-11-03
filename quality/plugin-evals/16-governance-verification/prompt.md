---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
Use verify-result to review this supplied hypothetical execution; no tools are
connected. User explicitly approved an unverified analysis after disclosure that
live governance authority was unavailable, and approved this exact plan:
count distinct canonical real customers with their first-ever order in September
2026, all channels, from shop.fct_orders. Real-account filtering is upstream.
Executed SQL:
SELECT COUNT(DISTINCT customer_id) AS new_customers FROM shop.fct_orders
WHERE is_first_order = TRUE AND order_date >= DATE '2026-09-01'
AND order_date < DATE '2026-10-01';
Execution succeeded and returned one row with new_customers = 42. No independent
snapshot or September completeness checks were supplied. No known revocation,
material defect, open decision or strict organizational restriction is present.
