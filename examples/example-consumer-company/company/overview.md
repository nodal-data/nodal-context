# Example Consumer Company — Overview

## What This Covers
What Example Consumer Company does and the unit of value it counts.

## Business model
Example Consumer Company is a direct-to-consumer subscription wellness app, sold
through the Apple/Google app stores and a direct web checkout.

## Core unit of value
The **subscription**. The core fact table `fct_subscription_periods` is a monthly
snapshot keyed at `subscription_id × billing_period` — NOT `subscription_id`. This
grain distinction is the single most common source of inflated subscriber counts,
since one subscription appears once per billing period it is active.
