#!/usr/bin/env python3
"""Assert the browser-binding state and user-facing setup lifecycle receipt."""

import json
import re
import sys
from pathlib import Path


def _load_object(path, label, problems):
    if not path.is_file():
        problems.append(f"missing {label}: {path.name}")
        return None
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        problems.append(f"malformed {label}: {path.name}")
        return None
    if not isinstance(value, dict):
        problems.append(f"{label} must be a JSON object: {path.name}")
        return None
    return value


def check_setup_lifecycle(project, transcript):
    project = Path(project).resolve()
    transcript = Path(transcript).resolve() if transcript else None
    problems = []

    config = _load_object(project / ".nodal.local.json", "Nodal configuration", problems)
    if config is not None:
        browser = config.get("browser")
        if not isinstance(browser, dict):
            problems.append(".nodal.local.json lacks a browser object")
        else:
            if browser.get("mode") != "automated":
                problems.append("browser mode is not automated")
            if browser.get("binding") != "chrome-devtools":
                problems.append("browser binding is not chrome-devtools")

    mcp = _load_object(project / ".mcp.json", "project MCP configuration", problems)
    if mcp is not None:
        servers = mcp.get("mcpServers")
        if not isinstance(servers, dict) or "chrome-devtools" not in servers:
            problems.append(".mcp.json lacks the chrome-devtools server binding")

    if transcript is None or not transcript.is_file():
        problems.append("missing non-interactive host transcript")
        return problems
    try:
        text = transcript.read_text()
    except OSError:
        problems.append(f"unreadable host transcript: {transcript}")
        return problems

    concepts = {
        "browser is optional": (r"\boptional\b",),
        "visible dedicated Chrome profile": (
            r"\bvisible\b",
            r"\bdedicated\b",
            r"\bchrome\b",
        ),
        "credential boundary": (r"\bcredentials?\b",),
        "configured binding": (r"\bconfigured\b",),
        "session restart": (r"\brestart\b",),
        "project-server approval": (r"\bapprov(?:e|al)\b",),
    }
    for label, patterns in concepts.items():
        if not all(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            problems.append(f"transcript does not communicate {label}")

    if not re.search(
        r"repeat\s+installation\s+offer\s*:\s*no\b",
        text,
        flags=re.IGNORECASE,
    ):
        problems.append("transcript lacks the no-repeat installation receipt")
    return problems


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(
            "usage: assert_setup_lifecycle.py PROJECT TRANSCRIPT",
            file=sys.stderr,
        )
        return 2
    problems = check_setup_lifecycle(argv[0], argv[1])
    if problems:
        print("assert_setup_lifecycle: FAILED", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("assert_setup_lifecycle: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
