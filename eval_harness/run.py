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

from . import adapters, client, report
from .grader import SKIPPED, grade


def _eval_domain(ncr, domain, status, model):
    """-> {domain, drafts, seeds:[{question, kind, off, on, on_reason}]}"""
    context = ncr.context_for(domain)
    judge_fn = lambda sql, expected: client.judge(sql, expected, model)
    rows = []
    for seed in ncr.seeds_for(domain, status):
        # value_at_snapshot (and unsupported kinds) are skipped without any LLM call
        if seed.kind not in ("sql_shape", "semantic_entity"):
            rows.append({"question": seed.question, "kind": seed.kind,
                         "off": SKIPPED, "on": SKIPPED, "on_reason": ""})
            continue
        off_sql = client.generate(seed.question, None, model)["sql"]
        on_sql = client.generate(seed.question, context, model)["sql"]
        off = grade(seed.expected, off_sql, judge_fn)
        on = grade(seed.expected, on_sql, judge_fn)
        rows.append({"question": seed.question, "kind": seed.kind,
                     "off": off.status, "on": on.status, "on_reason": on.reason})
    return {"domain": domain, "drafts": ncr.draft_count(domain), "seeds": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adapter", default="acf", help="context adapter (default: acf)")
    ap.add_argument("--domains", default="", help="comma-separated domains (empty = all)")
    ap.add_argument("--report", default="pr-comment", choices=["pr-comment"])
    ap.add_argument("--root", default=".", help="context repo root (default: .)")
    ap.add_argument("--status", default="confirmed",
                    help="seed status to score (default: confirmed; draft excluded)")
    ap.add_argument("--model", default=client.MODEL, help="Anthropic model id")
    ap.add_argument("--out", help="also write the report here")
    args = ap.parse_args(argv)

    requested = [d.strip() for d in args.domains.split(",") if d.strip()]

    builder = adapters.get_builder(args.adapter)
    ncr = builder(args.root, requested or None)
    domains = requested or ncr.domains()
    if not domains:
        print("eval_harness: no domains to evaluate")
        return 0

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
