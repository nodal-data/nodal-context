# Customer reference

## Routing

`active_customers` is the activity anchor; `new_customers` is the acquisition anchor.
For customer retention, use `methods/cohort-retention`. Clarify bare "retention"
between canonical customers returning and `subscriptions.renewal_rate` for terms.
Resolve `orders.customer_id` to `customers.customer_id`; exclude both test orders
and test customers in a composed cohort analysis. Use customers.segment or
customers.signup_year only when the chosen metric permits the slice.
