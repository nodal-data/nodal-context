---
max_turns: 8
timeout_seconds: 180
allowed_tools: [Skill, Read]
runs: 3
---
This query works and the numbers are already signed off. I just find the CASE-inside-SUM style hard to read. Can you rewrite it using CTEs so each measure is its own named step, keeping the output identical? I only want the rewritten SQL, nothing else needs checking.

```sql
SELECT
  ROUND(SUM(CASE WHEN measure_name = 'billed_revenue' THEN amount END), 2) AS billed_revenue,
  ROUND(SUM(CASE WHEN measure_name = 'collected_cash' THEN amount END), 2) AS collected_cash
FROM `nodal-shorelane.shorelane.fct_revenue`
WHERE measure_name IN ('billed_revenue', 'collected_cash')
  AND activity_date BETWEEN '2026-06-01' AND '2026-06-30'
```
