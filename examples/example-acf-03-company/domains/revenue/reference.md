# Revenue reference

## Routing

Ask for a basis before resolving bare "revenue". The `revenue_measures` family contains
`recognized_revenue`, `gmv`, `billed_revenue`, `net_revenue`, and `collected_cash`.
Every member sums `revenue_entries.amount` with its own `measure_name` constraint.
Use `activity_date` for that selected basis. Slice by channel or revenue_stream;
never add the five bases or subtract credits twice. Do not interpret collected_cash
as recognized_revenue. The refund-impact method is blocked pending a date decision.
