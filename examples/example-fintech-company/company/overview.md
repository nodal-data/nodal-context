# Example Fintech Company — Overview

## What This Covers
What Example Fintech Company does and the unit of value it counts.

## Business model
Example Fintech Company offers consumer installment loans, originated both directly
and through embedded partners (merchants who offer financing at checkout).

## Core unit of value
The **loan**. The core fact table `fct_loan_performance` is a monthly snapshot keyed
at `loan_id × statement_period` — NOT `loan_id`. This grain distinction is the single
most common source of inflated loan counts, since one loan appears once per month it
is on the books.
