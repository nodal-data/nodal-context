# Subscription Revenue Reference

> Agent-facing retrieval doc for Example Consumer Company subscription revenue.

## Quick Reference
- **Business context** — paid subscribers, recurring revenue, and churn for the
  subscription app.
- **Entity grain** — one row = subscription × billing_period (monthly snapshot). Use
  `COUNT(DISTINCT subscription_id)` for subscriber counts, never `COUNT(*)`.
- **Active subscriber** — `status = 'active'` in the current billing_period. Trials
  (`status = 'trialing'`) are NOT paid subscribers and are excluded from MRR.
- **Canonical table** — `FCT_SUBSCRIPTION_PERIODS`.

## Routing triggers
- IF question says **"active user"** vs **"active subscriber"** → DO NOT conflate.
  Active user = engagement (app open), lives in product analytics; active subscriber
  = paid status, lives in THIS table. They are different numbers.
- IF question is about **"revenue" / MRR** → use recognized revenue net of app-store
  fees (15–30%) and refunds; bookings (gross billed) is a different number. State
  which.
- IF question is about **"churn"** → DO NOT assume; clarify voluntary (user cancels)
  vs involuntary (failed payment — a large share of churn). Trials are excluded from
  the churn base.
- IF question filters by **platform** → app-store subscriptions carry the store fee
  and one platform reports billing on a delay; web subscriptions are full-margin.
- IF a metric spans the **snapshot grain** → pin to a single `billing_period` before
  aggregating, or subscribers double-count across months.

## Gotchas
- `COUNT(*)` overcounts subscribers because of the monthly-snapshot grain.
- Trials look like subscribers if filtered only by "active"-ish status.
- Gross bookings overstate revenue by the app-store fee.

## Cross-references
- engagement (active users, dim_user); trials (conversion subset of this table).
