"""Normalized Context Representation (NCR) — the intermediate every adapter maps into.

Per eval_harness/INTERFACE.md the format isn't the moat: every source (ACF, dbt docs,
raw markdown, …) collapses to this, and the delta is computed on it. Kept deliberately
small: the runner needs the seeds (ground truth) and a per-domain context blob to inject
for the context-on condition.
"""
from dataclasses import dataclass, field

# Contract version for the NCR shape + seed format (see INTERFACE.md "Versioning").
# Pre-1.0: the shape may change between minor releases without a deprecation cycle.
NCR_VERSION = 2


@dataclass
class Seed:
    question: str
    domain: str
    intent: str
    expected: dict          # {kind, must_include?, must_exclude?, entity?, value?, as_of?}
    provenance: str
    status: str             # draft | confirmed
    path: str = ""          # source file, for diagnostics
    ir: dict = field(default_factory=dict)  # optional structured decomposition
                            # {metric, dimensions?, filters?, grain?, time_window?}
                            # (schemas/ir.schema.json); empty for non-ACF sources
    approver: str = ""
    confirmed_at: str = ""
    variants: list = field(default_factory=list)
    verified_query_file: str = ""
    verification_source: dict = field(default_factory=dict)
    effective_status: str = ""
    blockers: list = field(default_factory=list)

    @property
    def eligibility(self):
        return self.effective_status or self.status

    @property
    def kind(self) -> str:
        return (self.expected or {}).get("kind", "")


@dataclass
class NCR:
    """seeds = ground truth (empty for non-ACF adapters); context_by_domain = the text
    injected for context-on, assembled from whatever the adapter found."""
    seeds: list = field(default_factory=list)
    context_by_domain: dict = field(default_factory=dict)
    definitions: dict = field(default_factory=dict)
    context_components: dict = field(default_factory=dict)
    capabilities: set = field(default_factory=set)
    diagnostics: list = field(default_factory=list)

    def domains(self):
        names = set(self.context_by_domain) | {s.domain for s in self.seeds}
        return sorted(n for n in names if n)

    def seeds_for(self, domain, status="confirmed"):
        return [s for s in self.seeds
                if s.domain == domain and (status is None or s.eligibility == status)]

    def draft_count(self, domain):
        return sum(1 for s in self.seeds if s.domain == domain and s.eligibility == "draft")

    def context_for(self, domain, relation="unresolved", target=None) -> str:
        components = self.context_components.get(domain)
        if not components:
            return self.context_by_domain.get(domain, "")
        parts = [components.get("definitions", ""), components.get("reference", "")]
        is_method = target and self.definitions.get(target, {}).get("kind") == "method"
        if relation != "equivalent" or is_method:
            parts.append(components.get("reasoning", ""))
        if relation in ("unresolved", "ambiguous", "related_only"):
            parts.append(components.get("orientation", ""))
        return "\n\n".join(p for p in parts if p)
