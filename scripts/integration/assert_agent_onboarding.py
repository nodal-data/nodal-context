#!/usr/bin/env python3
"""Assert the pre-install agent-guide handoff from an isolated Codex profile."""

import re
import sys
from pathlib import Path


PLUGIN_ID = "nodal-analytics@nodal"


def check_agent_onboarding(project, transcript, codex_home):
    project = Path(project).resolve()
    transcript = Path(transcript).resolve() if transcript else None
    codex_home = Path(codex_home).resolve()
    problems = []

    if not (project / "NODAL_AGENT_GUIDE.md").is_file():
        problems.append("clean project lacks NODAL_AGENT_GUIDE.md")
    for relative in (".nodal.local.json", ".mcp.json"):
        if (project / relative).exists():
            problems.append(f"onboarding wrote configuration before restart: {relative}")
    for relative in (".agents/skills", ".claude/skills"):
        if (project / relative).exists():
            problems.append(f"onboarding created duplicate project-local skills: {relative}")

    config_path = codex_home / "config.toml"
    if not config_path.is_file():
        problems.append("isolated Codex home lacks config.toml after onboarding")
    else:
        try:
            config_text = config_path.read_text()
        except OSError:
            problems.append("isolated Codex config.toml is unreadable")
        else:
            plugin_section = re.search(
                rf'^\[plugins\."{re.escape(PLUGIN_ID)}"\]\s*$'
                r"(?P<body>.*?)(?=^\[|\Z)",
                config_text,
                flags=re.MULTILINE | re.DOTALL,
            )
            if not plugin_section or not re.search(
                r"^enabled\s*=\s*true\s*$",
                plugin_section.group("body") if plugin_section else "",
                flags=re.MULTILINE,
            ):
                problems.append(f"isolated Codex home did not enable {PLUGIN_ID}")
            marketplace_section = re.search(
                r"^\[marketplaces\.nodal\]\s*$"
                r"(?P<body>.*?)(?=^\[|\Z)",
                config_text,
                flags=re.MULTILINE | re.DOTALL,
            )
            if not marketplace_section:
                problems.append("isolated Codex home lacks the nodal marketplace")
            elif not re.search(
                r'^source_type\s*=\s*"local"\s*$',
                marketplace_section.group("body"),
                flags=re.MULTILINE,
            ):
                problems.append("isolated Codex marketplace is not the local release candidate")

    if transcript is None or not transcript.is_file():
        problems.append("missing non-interactive host transcript")
        return problems
    try:
        text = transcript.read_text()
    except OSError:
        problems.append(f"unreadable host transcript: {transcript}")
        return problems

    concepts = {
        "Nodal analytics context": (r"\banalytics\b", r"\bcontext\b"),
        "single installation path": (r"\bexactly one\b|\bone\b.*\binstall",),
        "new-session boundary": (r"\b(?:new task|new session|restart)\b",),
        "setup handoff": (r"\bsetup-nodal\b",),
        "credential boundary": (r"\bcredentials?\b",),
    }
    for label, patterns in concepts.items():
        if not all(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            problems.append(f"transcript does not communicate {label}")

    receipts = {
        "Codex native-plugin installation": (
            r"installation\s+method\s*:\s*codex\s+native\s+plugin\b"
        ),
        "no duplicate installation": r"duplicate\s+installation\s*:\s*no\b",
        "no premature configuration": r"configuration\s+written\s*:\s*no\b",
        "restart and setup handoff": (
            r"next\s+task\s*:\s*restart\s+codex\s+and\s+invoke\s+\$?setup-nodal\b"
        ),
        "no credential request": r"credentials?\s+requested\s*:\s*no\b",
    }
    for label, pattern in receipts.items():
        if not re.search(pattern, text, flags=re.IGNORECASE):
            problems.append(f"transcript lacks receipt for {label}")
    return problems


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3:
        print(
            "usage: assert_agent_onboarding.py PROJECT TRANSCRIPT CODEX_HOME",
            file=sys.stderr,
        )
        return 2
    problems = check_agent_onboarding(argv[0], argv[1], argv[2])
    if problems:
        print("assert_agent_onboarding: FAILED", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("assert_agent_onboarding: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
