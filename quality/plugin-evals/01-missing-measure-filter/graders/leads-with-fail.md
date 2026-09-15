---
type: regex
target: last_message
match: contains
---
^(?:[^\n]*\n){0,2}[^\n]{0,80}\bFAIL\b
