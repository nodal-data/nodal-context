# Uncertainty v0

This is an interpretable placeholder for later calibration. It measures support
for the plan, not the probability that the eventual answer is correct.

## Features

Score each feature `0`, `0.5`, or `1`, multiply by its weight, and sum:

| Feature | Weight | `1` means |
|---|---:|---|
| interpretation uniqueness | 0.15 | one coherent reading; no unresolved parse |
| metric/entity resolution | 0.20 | every load-bearing term maps uniquely |
| temporal/scope anchoring | 0.10 | population, window, comparison, timezone explicit |
| authoritative context | 0.15 | selected meanings have governed human provenance |
| source agreement | 0.15 | credible sources agree or conflict was resolved |
| grain/join approval | 0.15 | grain and every join are governed and satisfiable |
| validated prior pattern | 0.10 | confirmed seed/query pattern supports this shape |

Use `0.5` for partial evidence. Use `0` for missing, contradicted, or purely
inferred evidence. Do not drop unavailable features and renormalize; missing
evidence is part of the uncertainty.

Levels:

- `high`: score >= 0.75
- `medium`: 0.45 <= score < 0.75
- `low`: score < 0.45
- `unknown`: the schema or context could not be inspected enough to score

Always emit:

```yaml
uncertainty:
  version: 0
  confidence_score: 0.0
  confidence_level: low
  calibrated: false
  features: {}
  drivers: []
  missing_evidence: []
  escalation:
    recommended: false
    reason: null
    target: null
```

The score is not a percentage. Say “uncalibrated heuristic” whenever displaying
the number to a user.

## Critical gates

Recommend escalation regardless of score when:

- two confirmed/governed sources conflict on the metric or population;
- metric meaning, grain, or a material time boundary remains unresolved;
- a many-to-many or otherwise unapproved join could change the answer;
- the requested output is not satisfiable from the inspected schema;
- a novel high-impact question has no owned definition or validated precedent;
- execution or post-query verification finds a material anomaly.

Prefer the domain owner named by the context. Otherwise recommend “data/analytics
owner”; do not invent a person. Medium confidence normally pauses for the user's
resolution. Low or unknown confidence recommends expert escalation and does not
execute while a critical gate remains.
