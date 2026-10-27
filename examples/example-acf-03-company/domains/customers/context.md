# Cohort reasoning

An activity cohort contains real customers who ordered in the base window. An
acquisition cohort contains customers whose first-ever eligible order was in that
window. Later acquisitions never enlarge a fixed cohort denominator. Return
activity is a membership test over the follow-up window, not a count of orders.
Sparse slices can have an empty denominator; null is distinct from observed churn.
