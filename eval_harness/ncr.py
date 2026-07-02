"""Normalized Context Representation (NCR) — the intermediate every adapter maps into.

Per eval-harness/INTERFACE.md the format isn't the moat: every source (ACF, dbt docs,
raw markdown, …) collapses to this, and the delta is computed on it. Kept deliberately
small: the runner needs the seeds (ground truth) and a per-domain context blob to inject
for the context-on condition.
"""
from dataclasses import dataclass, field


@dataclass
class Seed:
    question: str
    domain: str
    intent: str
    expected: dict          # {kind, must_include?, must_exclude?, entity?, value?, as_of?}
    provenance: str
    status: str             # draft | confirmed
    path: str = ""          # source file, for diagnostics

    @property
    def kind(self) -> str:
        return (self.expected or {}).get("kind", "")


@dataclass
class NCR:
    """seeds = ground truth (empty for non-ACF adapters); context_by_domain = the text
    injected for context-on, assembled from whatever the adapter found."""
    seeds: list = field(default_factory=list)
    context_by_domain: dict = field(default_factory=dict)

    def domains(self):
        names = set(self.context_by_domain) | {s.domain for s in self.seeds}
        return sorted(n for n in names if n)

    def seeds_for(self, domain, status="confirmed"):
        return [s for s in self.seeds
                if s.domain == domain and (status is None or s.status == status)]

    def draft_count(self, domain):
        return sum(1 for s in self.seeds if s.domain == domain and s.status == "draft")

    def context_for(self, domain) -> str:
        return self.context_by_domain.get(domain, "")
