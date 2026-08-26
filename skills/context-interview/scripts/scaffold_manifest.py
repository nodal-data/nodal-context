#!/usr/bin/env python3
"""Declarative artifact manifest for the installable context-repo scaffold.

Importing this module performs no filesystem access. Repository paths are the
canonical sources; ``skill_source`` paths are the generated distribution mirror
inside ``skills/context-interview``; ``target`` paths are destinations in a
generated analytics-context repository.
"""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Artifact:
    root_source: str
    skill_source: str
    target: Optional[str]
    fresh: bool = True
    upgrade: bool = True
    preserve: Tuple[str, ...] = ()


ARTIFACTS = (
    # Bootstrap files used from the installed skill but not copied onward.
    Artifact("scripts/scaffold.py", "scripts/scaffold.py", None),
    Artifact("scripts/scaffold_manifest.py", "scripts/scaffold_manifest.py", None),

    # Format and context-repo-local tooling.
    Artifact("SPEC.md", "references/SPEC.md", "SPEC.md"),
    Artifact("scripts/dbt_extract.py", "scripts/dbt_extract.py", "scripts/dbt_extract.py"),
    Artifact(
        "scripts/query_history_extract.py",
        "scripts/query_history_extract.py",
        "scripts/query_history_extract.py",
    ),
    Artifact("scripts/compile_skill.py", "scripts/compile_skill.py", "scripts/compile_skill.py"),

    # Fresh-only authoring scaffold. These rows deliberately retain dot paths.
    Artifact("template/.gitignore", "payload/template/.gitignore", ".gitignore", upgrade=False),
    Artifact("template/.claude", "payload/template/.claude", ".claude", upgrade=False),
    Artifact("template/AGENTS.md", "payload/template/AGENTS.md", "AGENTS.md", upgrade=False),
    Artifact("template/AUTHORING.md", "payload/template/AUTHORING.md", "AUTHORING.md", upgrade=False),
    Artifact("template/CLAUDE.md", "payload/template/CLAUDE.md", "CLAUDE.md", upgrade=False),
    Artifact("template/README.md", "payload/template/README.md", "README.md", upgrade=False),
    Artifact("template/SHARING.md", "payload/template/SHARING.md", "SHARING.md", upgrade=False),
    Artifact("template/company", "payload/template/company", "company", upgrade=False),
    Artifact(
        "template/context.config.yaml",
        "payload/template/context.config.yaml",
        "context.config.yaml",
        upgrade=False,
    ),
    Artifact("template/domains", "payload/template/domains", "domains", upgrade=False),
    Artifact("template/entities", "payload/template/entities", "entities", upgrade=False),
    Artifact("template/evals", "payload/template/evals", "evals", upgrade=False),

    # Support files refreshed on upgrade. Customer state is explicitly preserved.
    Artifact(
        ".ci",
        "payload/.ci",
        ".ci",
        preserve=(".ci/lineage-baseline.json",),
    ),
    Artifact("schemas", "payload/schemas", "schemas"),
    Artifact("eval_harness", "payload/eval_harness", "eval_harness"),
    Artifact("template/dbt-repo", "payload/dbt-repo", "dbt-repo"),
    Artifact(
        ".github/workflows/validate-context.yml",
        "payload/.github/workflows/validate-context.yml",
        ".github/workflows/validate-context.yml",
    ),
    Artifact(
        ".github/workflows/eval-delta.yml",
        "payload/.github/workflows/eval-delta.yml",
        ".github/workflows/eval-delta.yml",
    ),
    Artifact(
        ".github/workflows/context-drift.yml",
        "payload/.github/workflows/context-drift.yml",
        ".github/workflows/context-drift.yml",
    ),
)

IGNORED_NAMES = frozenset({"__pycache__", ".DS_Store", ".pytest_cache"})
IGNORED_SUFFIXES = (".pyc",)
REQUIRED_CONTEXT_MARKER = "context.config.yaml"

