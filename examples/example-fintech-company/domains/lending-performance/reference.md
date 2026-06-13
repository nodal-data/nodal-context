# Lending Performance Reference

> Agent-facing retrieval doc for Example Fintech Company lending performance.

## Quick Reference
- **Business context** — origination volume, outstanding balance, and credit
  performance for consumer installment loans.
- **Entity grain** — one row = loan × statement_period (monthly snapshot). Use
  `COUNT(DISTINCT loan_id)` for loan counts, never `COUNT(*)`.
- **Origination date** — use `disbursement_date`, NOT `application_date` or
  `approval_date`; many approved loans are never disbursed.
- **Canonical table** — `FCT_LOAN_PERFORMANCE`.

## Routing triggers
- IF question is about **"volume"** → DO NOT assume; clarify originated principal
  (new disbursements) vs outstanding balance (book on the books) vs repayment
  volume. Default to originated principal by `disbursement_date`.
- IF question is about **"default" / credit losses** → DO NOT conflate; charge-off
  is 90+ days past due, delinquency is 30+ DPD. State which.
- IF question filters by **partner** → one partner ("Partner Z") reports on a
  delayed cycle; EXCLUDE it from current-period originations unless told otherwise.
- IF question says **"active loan"** → means outstanding principal > 0, NOT
  `loan_status = 'active'` (which includes paid-ahead and deferred loans).
- IF a metric spans the **snapshot grain** → pin to a single `statement_period`
  before aggregating, or balances double-count across months.

## Gotchas
- `COUNT(*)` overcounts loans because of the monthly-snapshot grain.
- Approved ≠ disbursed; application-dated volume overstates originations.
- Partner Z's delayed reporting makes the most recent period look artificially low.

## Cross-references
- collections (repayments subset of this table); borrower-risk (dim_borrower).
