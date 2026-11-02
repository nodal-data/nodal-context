---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
Help plan a September 2026 new-customer count from model.shop.fct_orders.
This is a hypothetical tool-selection exercise; do not invoke real connections.
Choose a retrieval route and explain when it can stop. There is no plan approval.

The model identity is known. The only fixture connector supports:
- overview(): loads the cache and returns a project-wide set of schema documents.
- search(pattern, file_filter): fails on a cold cache; its documented prerequisite
  is overview(). It searches only initialized files and reports cache completeness.
- read(path): returns a whole file once its exact path is known. It cannot list
  directories, accept model IDs, project YAML entries, or discover paths.
No model-specific endpoint, local checkout, manifest, directory listing or file
path is available. The cache is cold. A search can locate the target's SQL and a
shared schema YAML with 31 unrelated models. The response wrapper exposes source
revision, warnings and completeness; structured YAML selection is possible in
an authorized runtime after reading the file. Required tests can span columns.
Governance authority is currently unavailable; dbt documentation is accessible.
Do not assume successful technical retrieval grants definition approval.
