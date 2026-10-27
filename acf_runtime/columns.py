"""Column aliases proven by complete, unambiguous manifest lineage.

No catalog guesses, SQL aliases or warehouse I/O. The maps are matching metadata,
not edits to authored definitions or permission to introduce a new dimension.
"""
from collections import defaultdict


def column_evidence(manifests, pointers):
    if not pointers:
        return {}, []
    records = {}
    for source, model in sorted(pointers):
        manifest = manifests.get(source)
        if not isinstance(manifest, dict):
            return {}, []  # incomplete lineage cannot establish uniqueness
        found = []
        for section in ("nodes", "sources"):
            for identifier, record in manifest.get(section, {}).items():
                if (record.get("resource_type") in ("model", "seed", "snapshot", "source")
                        and model in {record.get("name"), record.get("unique_id"), identifier}):
                    found.append((identifier, record))
        if len(found) != 1:
            return {}, []
        identifier, record = found[0]
        # Name and unique-ID pointers to one model do not create two candidates.
        key = (source, identifier)
        if key not in records:
            records[key] = (record, set())
        records[key][1].add(model)
    candidates = defaultdict(set)
    preferred = {}
    for (source, identifier), (record, pointers_for_model) in records.items():
        names = pointers_for_model | {record.get("name"), record.get("unique_id"), identifier}
        names.discard(None)
        for column in record.get("columns", {}):
            identity = (source, identifier, column)
            candidates[column].add(identity)
            for name in names:
                candidates[f"{name}.{column}"].add(identity)
            preferred[identity] = [f"{name}.{column}" for name in
                dict.fromkeys([record.get("name"), record.get("unique_id"), identifier]) if name]
    canonical = {identity: next((name for name in names if candidates[name] == {identity}), None)
                 for identity, names in preferred.items()}
    aliases = {}
    for name, matches in candidates.items():
        if len(matches) == 1:
            target = canonical[next(iter(matches))]
            if target is not None:
                aliases[name] = target
    ambiguous = sorted(name for name, matches in candidates.items() if len(matches) > 1)
    return aliases, ambiguous
