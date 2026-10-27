"""OSS one-shot eval-delta runner — CLI entry (`python -m eval_harness.run`).

  python -m eval_harness.run --adapter acf --domains "session-financials" --report pr-comment

For each requested domain: answer every confirmed seed context-off and context-on (one LLM
generation each), grade the SQL shape with an LLM judge, and print the delta report. No
warehouse; BYO ANTHROPIC_API_KEY only (no key -> graceful skip, exit 0, so CI stays green).
Honors the contract's free/paid line — see eval_harness/INTERFACE.md.
"""
import argparse
import sys
from pathlib import Path

from . import adapters, client, report, seeds as seeds_mod
from .grader import SKIPPED, grade_answer
from .matching import match_question, resolve
from dataclasses import asdict


def _eval_domain(ncr, domain, status, model):
    """Generate independently of seed answers; grade components with honest skips."""
    judge_fn = lambda evidence, expected: client.judge(evidence, expected, model)
    rows, truncated = [], False
    for seed in ncr.seeds_for(domain, status):
        method = None
        if seed.ir.get("method"):
            matches = resolve(seed.ir["method"], seed.domain, "method", ncr.definitions, aliases=False)
            if matches:
                method = ncr.definitions[matches[0]]
            else:
                rows.append({"question": seed.question, "kind": seed.kind, "off": SKIPPED,
                             "on": SKIPPED, "on_reason": "method without decisions/capability"})
                continue
        # No model call solely to compare a snapshot that cannot be executed here.
        if seed.kind == "value_at_snapshot" and method is None and not any(
                seed.expected.get(k) for k in ("must_include", "must_exclude")):
            rows.append({"question": seed.question, "kind": seed.kind, "off": SKIPPED,
                         "on": SKIPPED, "on_reason": "snapshot needs customer execution"})
            continue
        routing = {"relation": "unsupported", "blockers": []}
        if "matching" in ncr.capabilities:
            try:
                extracted = client.extract_ir(seed.question, domain, ncr.definitions, model)
                other_seeds = [{**asdict(s), "id": "seed:" + s.path.removeprefix("evals/seeds/")}
                               for s in ncr.seeds if s.path != seed.path]
                routing = match_question(extracted["ir"], domain, ncr.definitions, other_seeds,
                                         candidates=extracted.get("candidates"))
            except Exception:
                routing = {"relation": "unresolved", "blockers": ["IR extraction unavailable"]}
        context = ncr.context_for(domain, routing["relation"], routing.get("target"))
        if "matching" in ncr.capabilities and (routing.get("blockers") or routing["relation"] in ("ambiguous", "unresolved")):
            context = "Question routing: " + str({"relation": routing["relation"],
                         "blockers": routing.get("blockers", []),
                         "unsupported": routing.get("unsupported", [])}) + "\nClarify unresolved business semantics before a governed answer.\n\n" + context
        truncated |= len(context) > client.MAX_CONTEXT_CHARS
        off_answer = client.generate(seed.question, None, model)
        on_answer = client.generate(seed.question, context, model)
        off = grade_answer(seed.expected, off_answer, judge_fn, method=method)
        on = grade_answer(seed.expected, on_answer, judge_fn, method=method)
        rows.append({"question": seed.question, "kind": seed.kind, "off": off.status,
                     "on": on.status, "on_reason": on.reason, "routing": routing["relation"],
                     "off_components": off.components, "on_components": on.components})
    if truncated:
        print(f"eval_harness: WARNING: domain {domain!r} context was truncated; results may understate context.", file=sys.stderr)
    return {"domain": domain, "drafts": ncr.draft_count(domain) if status != "draft" else 0, "context_truncated": truncated,
            "selection": status, "seeds": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adapter", default="acf", help="context adapter (default: acf)")
    ap.add_argument("--mode", default="inject", choices=["inject"],
                    help="how context reaches the subject: 'inject' pastes the NCR "
                    "context into a single-call prompt (an 'mcp' mode — agent + MCP "
                    "configurations, measuring context+retrieval — is planned; see "
                    "INTERFACE.md 'Modes')")
    ap.add_argument("--domains", default="", help="comma-separated domains (empty = all)")
    ap.add_argument("--report", default="pr-comment", choices=["pr-comment"])
    ap.add_argument("--root", default=".", help="context repo root (default: .)")
    ap.add_argument("--seeds", help="directory of *.seed.yaml ground truth to attach — "
                    "required for adapters whose source carries no seeds "
                    "(dbt/ktx/raw/skill)")
    ap.add_argument("--status", default="confirmed", choices=["confirmed", "draft"],
                    help="seed status to score (default: confirmed; draft excluded)")
    ap.add_argument("--model", default=client.MODEL, help="Anthropic model id")
    ap.add_argument("--out", help="also write the report here")
    ap.add_argument("--branch-test", action="store_true", help="ACF only: test proposed context without approval")
    args = ap.parse_args(argv)

    requested = [d.strip() for d in args.domains.split(",") if d.strip()]

    builder = adapters.get_builder(args.adapter)
    ncr = builder(args.root, requested or None, branch_test=True) if args.adapter == "acf" and args.branch_test else builder(args.root, requested or None)
    if args.adapter == "acf" and (args.branch_test or __import__("os").environ.get("ACF_BRANCH_TEST") == "1"):
        print("BRANCH TEST: proposed context; results do not grant approval or establish live freshness.")
    if args.seeds:
        ncr.seeds.extend(seeds_mod.load_seeds(args.seeds))
    domains = requested or ncr.domains()
    if not domains:
        print("eval_harness: no domains to evaluate")
        return 0

    if not any(ncr.seeds_for(d, args.status) for d in domains):
        print("eval_harness: no seeds to grade — this context source carries no ground "
              "truth; point --seeds at a directory of *.seed.yaml files "
              f"(context domains found: {', '.join(ncr.domains()) or 'none'}).")
        return 0
    for d in domains:
        if ncr.seeds_for(d, args.status) and not ncr.context_for(d):
            print(f"eval_harness: WARNING: domain '{d}' has seeds but no context from "
                  f"adapter '{args.adapter}' (context domains: "
                  f"{', '.join(ncr.context_by_domain) or 'none'}); context-on will "
                  "equal context-off.", file=sys.stderr)

    if not client.available():
        print("eval_harness: ANTHROPIC_API_KEY not set; skipping eval (no delta computed).",
              file=sys.stderr)
        return 0

    results = [_eval_domain(ncr, d, args.status, args.model) for d in domains]

    text = report.render(results)
    print(text)
    if args.out:
        Path(args.out).write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
