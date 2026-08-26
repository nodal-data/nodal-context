#!/usr/bin/env python3
"""Lint Nodal skill metadata and local resource references."""
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("lint_skills: ERROR: PyYAML is required", file=sys.stderr)
    raise SystemExit(1)


ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
REFERENCE = re.compile(r"`(references/[A-Za-z0-9_.\-/]+)`")
MARKDOWN_LINK = re.compile(r"\[[^]]*\]\(([^)]+)\)")
HOST_ABSOLUTE = re.compile(r"(?:^|[\s`'(\"])(/(?:Users|home)/[^\s`)'\"]+)", re.MULTILINE)


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing opening frontmatter delimiter")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError("missing closing frontmatter delimiter")
    data = yaml.safe_load(parts[1])
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not an object")
    return data, text


def main():
    problems = []
    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        skill = skill_md.parent
        try:
            data, text = frontmatter(skill_md)
        except (ValueError, yaml.YAMLError) as exc:
            problems.append(f"{skill_md}: invalid frontmatter: {exc}")
            continue
        if data.get("name") != skill.name:
            problems.append(f"{skill_md}: name must match folder {skill.name!r}")
        description = data.get("description")
        if not isinstance(description, str) or not description.strip():
            problems.append(f"{skill_md}: description must be a non-empty string")
        elif len(description) > 300:
            problems.append(f"{skill_md}: description is not concise ({len(description)} > 300)")
        for match in HOST_ABSOLUTE.finditer(text):
            problems.append(f"{skill_md}: absolute host path: {match.group(1)}")
        for relative in REFERENCE.findall(text):
            if not (skill / relative).is_file():
                problems.append(f"{skill_md}: missing reference {relative}")
        for raw in MARKDOWN_LINK.findall(text):
            target = raw.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (skill_md.parent / target).resolve()
            try:
                resolved.relative_to(skill.resolve())
            except ValueError:
                problems.append(f"{skill_md}: link escapes skill folder: {raw}")
            else:
                if not resolved.exists():
                    problems.append(f"{skill_md}: missing linked resource: {raw}")
    if problems:
        for problem in problems:
            print(f"lint_skills: ERROR: {problem}", file=sys.stderr)
        return 1
    print(f"lint_skills: OK — {len(list(SKILLS.glob('*/SKILL.md')))} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

