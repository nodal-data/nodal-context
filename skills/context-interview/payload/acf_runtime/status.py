"""Dependency eligibility, kept separate from authored approval metadata."""


def resolve_status(nodes):
    """Monotone fixed point handles even invalid graphs without recursion."""
    for node in nodes.values():
        node.blocking_reasons = set(node.local_blockers)
        if node.data.get("status") == "draft":
            node.blocking_reasons.add("authored_draft")
    changed = True
    while changed:
        changed = False
        for node in nodes.values():
            for target in node.dependencies:
                dependency = nodes.get(target)
                if dependency is None or dependency.blocking_reasons:
                    reason = f"dependency:{target}"
                    if reason not in node.blocking_reasons:
                        node.blocking_reasons.add(reason)
                        changed = True
    for node in nodes.values():
        node.effective_status = "draft" if node.blocking_reasons else "confirmed"
