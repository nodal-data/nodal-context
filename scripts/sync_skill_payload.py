#!/usr/bin/env python3
"""Write or verify the generated context-interview distribution mirror."""
import argparse
import hashlib
import shutil
import stat
import sys
from pathlib import Path

from scaffold_manifest import ARTIFACTS, IGNORED_NAMES, IGNORED_SUFFIXES


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "context-interview"


def ignored(path):
    return path.name in IGNORED_NAMES or path.name.endswith(IGNORED_SUFFIXES)


def files_under(path):
    if path.is_file() or path.is_symlink():
        return {Path()}
    return {
        item.relative_to(path)
        for item in path.rglob("*")
        if (item.is_file() or item.is_symlink())
        and not ignored(item)
        and not any(ignored(part) for part in item.relative_to(path).parents)
    }


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.digest()


def expected_files():
    expected = {}
    for artifact in ARTIFACTS:
        source = ROOT / artifact.root_source
        for relative in files_under(source) if source.exists() else {Path()}:
            destination = Path(artifact.skill_source) / relative
            if destination in expected:
                raise ValueError(f"duplicate generated destination: {destination}")
            expected[destination] = source / relative
    return expected


GENERATED_TREES = (Path("payload"), Path("scripts"))


def generated_files_outside_trees():
    return {
        Path(a.skill_source)
        for a in ARTIFACTS
        if not any(Path(a.skill_source).is_relative_to(tree) for tree in GENERATED_TREES)
    }


def actual_files():
    actual = set()
    for top in GENERATED_TREES:
        root = SKILL / top
        if not root.exists():
            continue
        for item in root.rglob("*"):
            if (item.is_file() or item.is_symlink()) and not ignored(item):
                actual.add(item.relative_to(SKILL))
    for relative in generated_files_outside_trees():
        path = SKILL / relative
        if path.is_file() or path.is_symlink():
            actual.add(relative)
    return actual


def compare():
    expected = expected_files()
    actual = actual_files()
    missing = sorted(set(expected) - actual, key=str)
    extra = sorted(actual - set(expected), key=str)
    divergent = []
    mode_divergent = []
    for relative in sorted(set(expected) & actual, key=str):
        source, destination = expected[relative], SKILL / relative
        if source.is_symlink() != destination.is_symlink():
            divergent.append(relative)
        elif source.is_symlink():
            if source.readlink() != destination.readlink():
                divergent.append(relative)
        elif digest(source) != digest(destination):
            divergent.append(relative)
        if stat.S_IMODE(source.lstat().st_mode) != stat.S_IMODE(destination.lstat().st_mode):
            mode_divergent.append(relative)
    return missing, extra, divergent, mode_divergent


def write():
    expected = expected_files()
    for top in GENERATED_TREES:
        path = SKILL / top
        if path.exists():
            shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink()
    for relative in generated_files_outside_trees():
        path = SKILL / relative
        if path.exists() or path.is_symlink():
            path.unlink()
    for relative, source in sorted(expected.items(), key=lambda item: str(item[0])):
        destination = SKILL / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            destination.symlink_to(source.readlink())
        else:
            shutil.copy2(source, destination)
    print(f"sync_skill_payload: wrote {len(expected)} files")


def check():
    labels = ("missing", "extra", "content-divergent", "mode-divergent")
    groups = compare()
    failed = False
    for label, paths in zip(labels, groups):
        if paths:
            failed = True
            for path in paths:
                print(f"{label}: {path}")
    if failed:
        return 1
    print(f"sync_skill_payload: OK — {len(expected_files())} files synchronized")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        write()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
