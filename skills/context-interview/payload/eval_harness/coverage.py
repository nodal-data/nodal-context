"""Three independent coverage levels over a format-neutral definition registry.

Pure calculations only: adapters supply verification capability/evidence states.
No model calls, filesystem reads, writes, credential handling or implicit execution.
"""
from collections import Counter
from copy import deepcopy

from .matching import normalize, stable


def cell(normalized):
    return {**deepcopy(normalized.identity), "time_window": normalized.ir.get("time_window")}


def build_report(definitions, seeds, queue=None, time_tokens=(), verification=None, all_cells=False):
    verification = verification or {}
    targets, cells = {}, {}
    for key, definition in sorted(definitions.items()):
        if not definition.get("defined"):
            state = "undefined"
        elif definition.get("effective_status", "draft") != "confirmed":
            state = "blocked_or_draft"
        elif definition.get("kind") == "metric" and not definition.get("expressible", False):
            state = "defined_not_expressible"
        else:
            state = "defined"
        targets[key] = {"definition": state, "blockers": definition.get("blockers", []),
                        "slicing": [], "verification": []}
    orphan, unindexed, stale, negatives, variants = [], [], [], Counter(), {}
    for seed in seeds:
        key = seed["id"]
        variants[key] = len(seed.get("variants", []))
        if seed.get("expected", {}).get("kind") == "negative":
            negatives[seed["expected"]["reason"]] += 1
            continue
        if not seed.get("ir"):
            unindexed.append(key)
            continue
        normalized = normalize(seed["ir"], seed["domain"], definitions, question=False)
        if normalized.state != "resolved":
            orphan.append({"seed": key, "reasons": normalized.unsupported or ["target_unresolved"]})
            continue
        c = cell(normalized); signature = stable(c)
        row = cells.setdefault(signature, {"cell": c, "target": normalized.target,
                               "seed_ids": [], "verified_seed_ids": [], "demand": 0})
        reasons = list(seed.get("blockers", [])) + normalized.blockers
        if seed.get("effective_status", seed.get("status", "draft")) != "confirmed":
            reasons.append("seed_not_confirmed")
        evidence = verification.get(key, {"state": "unverified", "verified": False})
        reasons.extend(evidence.get("stale_reasons", []))
        if reasons:
            stale.append({"seed": key, "reasons": sorted(set(reasons))})
        # Missing replay evidence does not erase definition/slice human approval.
        semantic_stale = [r for r in reasons if r not in evidence.get("stale_reasons", [])]
        if not semantic_stale:
            row["seed_ids"].append(key)
            if evidence.get("verified"):
                row["verified_seed_ids"].append(key)
        targets[normalized.target]["verification"].append({"seed": key, **evidence})
    unresolved_demand = []
    for observed in queue or []:
        # Disposed observations remain demand evidence; count each event ID once upstream.
        normalized = normalize(observed.get("ir"), observed.get("domain", ""), definitions)
        if observed.get("relation") == "ambiguous" or normalized.state != "resolved":
            unresolved_demand.append({"id": observed["id"], "count": observed["count"],
                                      "relation": "ambiguous" if observed.get("relation") == "ambiguous" else normalized.state,
                                      "reasons": normalized.unsupported or normalized.blockers})
            continue
        c = cell(normalized); signature = stable(c)
        row = cells.setdefault(signature, {"cell": c, "target": normalized.target,
                               "seed_ids": [], "verified_seed_ids": [], "demand": 0})
        row["demand"] += observed["count"]
    if all_cells:
        for key, definition in definitions.items():
            if definition.get("kind") != "metric" or not definition.get("defined"):
                continue
            for dims in [[], *([d] for d in sorted(definition.get("dimensions", [])))]:
                for token in time_tokens:
                    normalized = normalize({"metric": key, "dimensions": dims, "time_window": token},
                                           definition["domain"], definitions, question=False)
                    if normalized.state != "resolved":
                        continue
                    c = cell(normalized)
                    cells.setdefault(stable(c), {"cell": c, "target": key, "seed_ids": [], "verified_seed_ids": [], "demand": 0})
    uncovered = []
    for signature, row in sorted(cells.items()):
        row["slice_covered"] = bool(row["seed_ids"])
        row["verification_covered"] = bool(row["verified_seed_ids"])
        targets[row["target"]]["slicing"].append(row)
        if not row["slice_covered"] and (row["demand"] or all_cells):
            uncovered.append(row)
    uncovered.sort(key=lambda row: (-row["demand"], stable(row["cell"])))
    return {"schema_version": 1, "targets": targets, "uncovered": uncovered,
            "unresolved_demand": sorted(unresolved_demand, key=lambda r: (-r["count"], r["id"])),
            "demand_available": queue is not None,
            "queue_depth": None if queue is None else sum(q["status"] == "pending" for q in queue),
            "stale_seeds": stale, "orphan_seeds": orphan, "unindexed_seeds": unindexed,
            "negative_seeds": dict(sorted(negatives.items())), "variants_per_seed": variants,
            "denominator": "Seeded/observed cells; --all adds aggregate and singleton metric dimensions x declared tokens. Not all possible questions."}


def render(report):
    lines = ["# Context coverage", "", report["denominator"], "",
             "| Target | Definition | Seeded slices | Verified slices |", "|---|---|---:|---:|"]
    for key, target in report["targets"].items():
        rows = target["slicing"]
        lines.append(f"| {key} | {target['definition']} | {sum(r['slice_covered'] for r in rows)}/{len(rows)} | {sum(r['verification_covered'] for r in rows)}/{len(rows)} |")
    lines += ["", "Observed demand: " + (f"{report['queue_depth']} pending entries" if report["demand_available"] else "unknown (no queue)"),
              "", "## Demand-ranked uncovered cells", ""]
    lines += [f"- {r['demand']} observations: `{stable(r['cell'])}`" for r in report["uncovered"]] or ["None in the reported universe."]
    for title, key in (("Stale seeds", "stale_seeds"), ("Orphan seeds", "orphan_seeds"),
                       ("Unresolved demand", "unresolved_demand")):
        lines += ["", f"## {title}", ""]
        lines += [f"- `{stable(item)}`" for item in report[key]] or ["None."]
    lines += ["", "## Verification evidence", ""]
    entries = [item for target in report["targets"].values() for item in target["verification"]]
    lines += [f"- `{item['seed']}`: {item['state']}" + (f"; {item['query']}" if item.get("query") else "")
              for item in entries] or ["None."]
    lines += ["", f"Negative seeds by reason: `{stable(report['negative_seeds'])}`",
              f"Variants per seed: `{stable(report['variants_per_seed'])}`",
              f"Unindexed seeds: `{stable(report['unindexed_seeds'])}`"]
    return "\n".join(lines) + "\n"
