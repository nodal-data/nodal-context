# Example Healthcare Company — Overview

## What This Covers
What Example Healthcare Company does and the unit of value it counts. 

## Business model
Example Healthcare Company delivers ABA / behavioral health care through a network of care provider
companies (CPCs), including its own internal network.

## Core unit of value
The **session** (a delivered unit of care). The core fact table
`fct_session_financials` is keyed at `note_id × authorized_service_id` — NOT
`note_id`. This grain distinction is the single most common source of wrong
session counts.
