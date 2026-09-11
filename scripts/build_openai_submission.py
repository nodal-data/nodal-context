#!/usr/bin/env python3
"""Build the uploadable OpenAI skills-only plugin archive."""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INCLUDED = (
    Path("plugin.json"),
    Path(".codex-plugin"),
    Path("skills"),
    Path("assets"),
    Path("LICENSE"),
    Path("README.md"),
)


def should_skip(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def copy_payload(staging: Path) -> None:
    for relative in INCLUDED:
        source = ROOT / relative
        target = staging / relative
        if source.is_dir():
            shutil.copytree(
                source,
                target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def normalize_openai_skill_metadata(staging: Path) -> None:
    """Remove a Claude-only restriction while retaining OpenAI's explicit policy."""
    setup_skill = staging / "skills/setup-nodal/SKILL.md"
    contents = setup_skill.read_text(encoding="utf-8")
    marker = "disable-model-invocation: true"
    if contents.count(marker) != 1:
        raise RuntimeError("setup-nodal must contain exactly one Claude invocation marker")
    setup_skill.write_text(contents.replace(marker, "disable-model-invocation: false"), encoding="utf-8")


def write_archive(staging: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(staging.rglob("*")):
            if not path.is_file() or should_skip(path):
                continue
            relative = path.relative_to(staging)
            info = zipfile.ZipInfo.from_file(path, arcname=relative.as_posix())
            mode = path.stat().st_mode
            info.external_attr = (stat.S_IMODE(mode) & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main(argv: list[str] | None = None) -> int:
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    default_output = ROOT / "dist" / f"{manifest['name']}-{manifest['version']}-openai.zip"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_output)
    args = parser.parse_args(argv)
    output = args.output.expanduser().resolve()

    with tempfile.TemporaryDirectory(prefix="nodal-openai-submission-") as raw_staging:
        staging = Path(raw_staging)
        copy_payload(staging)
        normalize_openai_skill_metadata(staging)
        write_archive(staging, output)

    print(f"build_openai_submission: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
