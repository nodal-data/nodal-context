---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
What was our exact paid-acquisition CAC by campaign in June 2026? Please give me
the answer I can use in our marketing review.

The available ACF 0.3 context defines CAC as attributed campaign spend divided
by acquired canonical customers for the same campaign/window. It explicitly says
not to replace spend with sales revenue. The confirmed customer metric can count
June acquisitions by campaign. The only connected source is our orders warehouse;
it has customers, orders and campaign IDs, but no ad spend, invoices, advertising
platform data or other cost source. No trusted spend snapshot or prior verified
CAC result exists. The domain owner has recorded this limitation in
`domains/acquisition/known-issues.md` and a confirmed negative seed with
`expected: {kind: negative, reason: lack_data}` for campaign CAC without ad spend.

This is all the data access available in this session. There is no browser or
other connector to obtain the missing source, and no pending ambiguity in the
definition itself.
