"""Render the on/off/perfect delta report (the `--report pr-comment` markdown).

Pure: takes already-computed per-domain results, returns a markdown string. Shape follows
eval-harness/INTERFACE.md — three percentages + the "still wrong with context on" punch-list.
"""
from .grader import PASS, FAIL, SKIPPED


def _bar(pct, width=16):
    filled = round((pct / 100) * width)
    return "█" * filled + "░" * (width - filled)


def _pct(passes, total):
    return None if total == 0 else round(100 * passes / total)


def render(domain_results) -> str:
    """domain_results: [{domain, drafts, seeds:[{question, kind, off, on, on_reason}]}]"""
    out = ["## Eval delta — context on/off (OSS one-shot)", ""]
    for dr in domain_results:
        seeds = dr["seeds"]
        gradable = [s for s in seeds if s["off"] != SKIPPED]
        skipped = len(seeds) - len(gradable)
        off = _pct(sum(s["off"] == PASS for s in gradable), len(gradable))
        on = _pct(sum(s["on"] == PASS for s in gradable), len(gradable))

        out.append(
            f"### Domain: {dr['domain']}   "
            f"(seeds: {len(seeds)} confirmed, {dr.get('drafts', 0)} draft excluded, "
            f"{skipped} value_at_snapshot skipped)")
        if not gradable:
            out.append("- no gradable seeds (all skipped — value_at_snapshot needs a "
                       "warehouse, the paid live-execution path)")
            out.append("")
            continue
        delta = f"  (+{on - off} pts)" if on is not None and off is not None else ""
        out.append(f"- context-off → {off}%  {_bar(off)}")
        out.append(f"- context-on  → {on}%  {_bar(on)}{delta}")
        out.append("- perfect     → 100%")

        punch = [s for s in gradable if s["on"] == FAIL]
        if punch:
            out.append("")
            out.append("Still wrong with context on (the punch-list):")
            for s in punch:
                reason = (s.get("on_reason") or "").strip()
                out.append(f'  • "{s["question"]}"  {reason}  [{s["kind"]}]')
        out.append("")

    if len(out) <= 2:
        out.append("_No domains evaluated._")
    return "\n".join(out).rstrip() + "\n"
