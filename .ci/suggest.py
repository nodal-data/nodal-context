#!/usr/bin/env python3
"""Optional LLM step: turn a drift report into *draft* ACF edit suggestions.

Runs only when ANTHROPIC_API_KEY is set. Reads the markdown report produced by
`.ci/drift.py`, loads the context files it flagged, and asks Claude to draft concrete
edits — always `status: draft`, tagged `# dbt-derived`, for a human to confirm. This
preserves the repo's core invariant: the model drafts, the analyst owns every
definition (see CLAUDE.md / README.md). It NEVER edits files; it only writes a
suggestion block the reconciliation PR/issue can carry.

  python .ci/suggest.py --report drift-report.md --out drift-suggestions.md

This is the BYO-key path: it runs in the customer's own GitHub Action with the
customer's key, so reconciliation costs Nodal nothing and no data leaves their repo.
"""
import argparse
import os
import re
import sys
from pathlib import Path

MODEL = "claude-opus-4-8"
# Bound what we send so a huge drift never blows up the request.
MAX_FILE_CHARS = 8000
MAX_FILES = 20

SYSTEM = (
    "You help maintain an Analytics Context Format (ACF) repository. dbt models that "
    "feed the context changed, and the context may now be stale. Propose concrete, "
    "minimal edits to the named context files.\n\n"
    "Hard rules — the repo's reason to exist depends on these:\n"
    "- A human owns every definition. You DRAFT; the analyst confirms. Mark every new "
    "or changed field `status: draft`.\n"
    "- Tag each dbt-derived suggestion with a `# dbt-derived` comment so its origin is "
    "auditable.\n"
    "- No statistics or numbers — qualitative business logic only.\n"
    "- Do not invent business meaning. If a change needs analyst knowledge you don't "
    "have, say so as a question instead of guessing.\n"
    "Output a short markdown section per affected file: the suggested edit in a fenced "
    "block, then one line on why. Keep it skimmable."
)


def _warn(msg):
    print(f"suggest: {msg}", file=sys.stderr)


def affected_files(report_text):
    """Pull the context file paths drift.py listed (domains/<d>/<file>)."""
    paths = re.findall(r"domains/[^\s,]+?\.(?:yaml|md)", report_text)
    # dedupe, preserve order
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:MAX_FILES]


def build_prompt(report_text, repo_root):
    parts = ["# Drift report\n", report_text, "\n\n# Current content of affected files\n"]
    for rel in affected_files(report_text):
        f = repo_root / rel
        if not f.exists():
            parts.append(f"\n## {rel}\n(missing on disk)\n")
            continue
        body = f.read_text()[:MAX_FILE_CHARS]
        parts.append(f"\n## {rel}\n```\n{body}\n```\n")
    parts.append("\nPropose draft edits for these files based on the drift above.")
    return "".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", default="drift-report.md")
    ap.add_argument("--out", default="drift-suggestions.md")
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        _warn("ANTHROPIC_API_KEY not set; skipping LLM suggestions")
        return 0
    report = Path(args.report)
    if not report.exists():
        _warn(f"{args.report} not found; nothing to suggest on")
        return 0

    try:
        import anthropic
    except ImportError:
        _warn("anthropic SDK not installed (pip install anthropic); skipping")
        return 0

    client = anthropic.Anthropic()
    prompt = build_prompt(report.read_text(), Path(args.repo_root))

    # Streaming so a large suggestion can't hit the request timeout; adaptive thinking
    # because mapping a dbt diff to careful draft edits benefits from reasoning.
    with client.messages.stream(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    text = "".join(b.text for b in message.content if b.type == "text").strip()
    if not text:
        _warn("model returned no suggestions")
        return 0

    body = "## Suggested draft edits (LLM-generated, unconfirmed)\n\n" + text + "\n"
    Path(args.out).write_text(body)
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
