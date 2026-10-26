#!/usr/bin/env python3
"""Optional LLM step: turn a drift report into *draft* ACF edit suggestions.

Runs only when ANTHROPIC_API_KEY is set. Reads the markdown report produced by
`.ci/drift.py`, loads the context files it flagged, and asks Claude to draft concrete
edits on a working branch, tagged `# dbt-derived`, for human review and merge. This
preserves the repo's core invariant: the model drafts, the analyst owns every
definition (see CLAUDE.md / README.md). It NEVER edits files; it only writes a
suggestion block the reconciliation PR/issue can carry.

  python .ci/suggest.py --report .nodal/drift-report.md --out .nodal/drift-suggestions.md

This is the BYO-key path: it runs in the customer's own GitHub Action with the
customer's key. The selected context/report is sent to the customer's model
provider. This optional local helper is not part of automatic status publication.
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime.verified import contained, atomic_private

MODEL = "claude-opus-4-8"
# Bound what we send so a huge drift never blows up the request.
MAX_FILE_CHARS = 8000
MAX_FILES = 20
MAX_REPORT_CHARS = 24000
MAX_OUTPUT_CHARS = 32000

SYSTEM = (
    "You help maintain an Analytics Context Format (ACF) repository. dbt models that "
    "feed the context changed, and the context may now be stale. Propose concrete, "
    "minimal edits to the named context files.\n\n"
    "Hard rules — the repo's reason to exist depends on these:\n"
    "- A human owns every definition. Propose working-branch edits without authored status. "
    "Protected human-reviewed merge is the approval mechanism. "
    "Preserve old human attribution; never invent approver or confirmed_at.\n"
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
    """Only 0.3 authored-context paths; never seeds, caches or notebook sidecars."""
    paths = re.findall(
        r"(?<![\w/.-])(?:domains/[A-Za-z0-9_-]+/(?:(?:metrics/[A-Za-z_][A-Za-z0-9_-]*|domain|entities)\.yaml|"
        r"(?:context|reference|known-issues)\.md)|entities/[A-Za-z_][A-Za-z0-9_-]*\.yaml|"
        r"methods/[A-Za-z_][A-Za-z0-9_-]*\.md|company/(?:overview|terminology)\.md)(?![A-Za-z0-9/.-])", report_text)
    # dedupe, preserve order
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:MAX_FILES]


def build_prompt(report_text, repo_root):
    if len(report_text) > MAX_REPORT_CHARS:
        raise ValueError("report exceeds suggestion limit")
    parts = ["# Drift report\n", report_text, "\n\n# Current content of affected files\n"]
    for rel in affected_files(report_text):
        try:
            f = contained(repo_root, rel, ".")
        except ValueError:
            parts.append(f"\n## {rel}\n(unavailable; path rejected)\n")
            continue
        if not f.exists():
            parts.append(f"\n## {rel}\n(missing on disk)\n")
            continue
        if f.stat().st_size > MAX_FILE_CHARS:
            parts.append(f"\n## {rel}\n(omitted: input limit; ask the analyst instead of inferring content)\n")
            continue
        body = f.read_text()
        parts.append(f"\n## {rel}\n```\n{body}\n```\n")
    parts.append("\nPropose draft edits for these files based on the drift above.")
    return "".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", default=".nodal/drift-report.md")
    ap.add_argument("--out", default=".nodal/drift-suggestions.md")
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

    try:
        prompt = build_prompt(report.read_text(), Path(args.repo_root))
        destination = contained(args.repo_root, args.out, ".nodal")
        client = anthropic.Anthropic(timeout=60, max_retries=0)

        # A bounded, optional request; failure never substitutes for human review.
        with client.messages.stream(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()
        text = "".join(b.text for b in message.content if b.type == "text").strip()
    except Exception:
        _warn("context or model unavailable; no suggestions produced")
        return 0

    if not text or len(text) > MAX_OUTPUT_CHARS:
        _warn("model returned empty or oversized suggestions")
        return 0

    body = "## Suggested draft edits (LLM-generated, unconfirmed)\n\n" + text + "\n"
    try:
        atomic_private(destination, body.encode(), overwrite=True)
    except (ValueError, OSError):
        _warn("local suggestion output unavailable")
        return 0
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
