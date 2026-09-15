---
type: regex
target: last_message
match: not_contains
---
^(?:[^\n]*\n){0,2}[^\n]{0,80}\b(PASS|WARN|FAIL)\b
