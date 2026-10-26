"""Report paired positive delta, separate escalation accuracy and component gaps."""
from .grader import PASS, FAIL, SKIPPED


def _bar(pct, width=16):
    filled = round((pct / 100) * width)
    return "█" * filled + "░" * (width - filled)


def _pct(passes, total):
    return None if total == 0 else round(100 * passes / total)


def render(domain_results):
    out = ["## Eval delta — context on/off (OSS one-shot)", ""]
    for dr in domain_results:
        seeds = dr["seeds"]
        positives = [s for s in seeds if s["kind"] != "negative"]
        paired = [s for s in positives if s["off"] in (PASS, FAIL) and s["on"] in (PASS, FAIL)]
        snapshot_skips = sum(s["kind"] == "value_at_snapshot" and SKIPPED in (s["off"], s["on"]) for s in positives)
        out += [f"### Domain: {dr['domain']}   (seeds: {len(seeds)} {dr.get('selection', 'confirmed')}, "
                f"{dr.get('drafts', 0)} draft excluded, {snapshot_skips} value_at_snapshot skipped)"]
        if dr.get("selection") == "draft":
            out.append("- Draft/simulated evaluation; this is not human-verified coverage.")
        if dr.get("context_truncated"):
            out.append("- Context was **truncated**; the delta may understate this context.")
        if paired:
            off = _pct(sum(s["off"] == PASS for s in paired), len(paired))
            on = _pct(sum(s["on"] == PASS for s in paired), len(paired))
            out += [f"- context-off → {off}%  {_bar(off)}",
                    f"- context-on  → {on}%  {_bar(on)}  ({on - off:+d} pts)",
                    f"- Paired positive denominator: {len(paired)}; {len(positives)-len(paired)} incompletely graded seeds excluded."]
        else:
            out.append("- No fully paired positive scores; missing execution/judge evidence is skipped.")
        negatives = [s for s in seeds if s["kind"] == "negative"]
        if negatives:
            out += ["", "Escalation accuracy (excluded from positive delta):"]
            for mode in ("off", "on"):
                scored = [s for s in negatives if s[mode] in (PASS, FAIL)]
                passed = sum(s[mode] == PASS for s in scored)
                score = f"{_pct(passed, len(scored))}%" if scored else "unscored"
                out.append(f"- context-{mode}: {score} ({passed}/{len(scored)}); {len(negatives)-len(scored)} skipped")
        components = {}
        for seed in positives:
            for mode in ("off", "on"):
                for name, result in seed.get(mode + "_components", {}).items():
                    components.setdefault((mode, name), []).append(result["status"])
        if components:
            out += ["", "Component checks (partial results do not imply full verification):"]
            for (mode, name), statuses in sorted(components.items()):
                scored = sum(s in (PASS, FAIL) for s in statuses)
                out.append(f"- {mode}/{name}: {statuses.count(PASS)}/{scored} passed; {statuses.count(SKIPPED)} skipped")
        punch = [s for s in seeds if s["on"] == FAIL]
        if punch:
            out += ["", "Still wrong with context on (the punch-list):"]
            for seed in punch:
                out.append(f'  • "{seed["question"]}"  {(seed.get("on_reason") or "").strip()}  [{seed["kind"]}]')
        out.append("")
    if len(out) <= 2:
        out.append("_No domains evaluated._")
    return "\n".join(out).rstrip() + "\n"
