#!/usr/bin/env python3
"""Validate the Codex manifest/marketplace paths and list available plugins."""
import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / ".codex-plugin/plugin.json"
MARKETPLACE_PATH = ROOT / ".agents/plugins/marketplace.json"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def load(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def validate():
    problems = []
    manifest = load(MANIFEST_PATH)
    for key in ("name", "version", "description", "author", "license", "skills", "interface"):
        if key not in manifest:
            problems.append(f"manifest missing {key}")
    if not SEMVER.match(str(manifest.get("version", ""))):
        problems.append("manifest version is not strict semver")
    if manifest.get("license") != "Apache-2.0":
        problems.append("manifest license must be Apache-2.0")
    if "mcpServers" in manifest:
        problems.append("manifest must not bundle an MCP server")
    skill_path = (ROOT / str(manifest.get("skills", ""))).resolve()
    if skill_path != (ROOT / "skills").resolve() or not skill_path.is_dir():
        problems.append("manifest skills path must resolve to root skills/")

    marketplace = load(MARKETPLACE_PATH)
    entries = marketplace.get("plugins")
    if not isinstance(entries, list) or not entries:
        problems.append("marketplace plugins must be a non-empty array")
        entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append("marketplace plugin entry must be an object")
            continue
        source = entry.get("source")
        if not isinstance(source, dict) or source.get("source") != "local":
            problems.append(f"{entry.get('name')}: source must be local")
            continue
        raw_path = source.get("path")
        if not isinstance(raw_path, str) or not raw_path.startswith("./"):
            problems.append(f"{entry.get('name')}: source path must start with ./")
            continue
        plugin_root = (ROOT / raw_path).resolve()
        try:
            plugin_root.relative_to(ROOT.resolve())
        except ValueError:
            problems.append(f"{entry.get('name')}: source path escapes marketplace root")
            continue
        plugin_manifest = plugin_root / ".codex-plugin/plugin.json"
        if not plugin_manifest.is_file():
            problems.append(f"{entry.get('name')}: source has no .codex-plugin/plugin.json")
        elif load(plugin_manifest).get("name") != entry.get("name"):
            problems.append(f"{entry.get('name')}: marketplace/manifest name mismatch")
        policy = entry.get("policy")
        if not isinstance(policy, dict) or not {"installation", "authentication"} <= set(policy):
            problems.append(f"{entry.get('name')}: incomplete policy")
        if not entry.get("category"):
            problems.append(f"{entry.get('name')}: missing category")

    setup_yaml = ROOT / "skills/setup-nodal/agents/openai.yaml"
    if "allow_implicit_invocation: false" not in setup_yaml.read_text(encoding="utf-8"):
        problems.append("setup-nodal must disable implicit Codex invocation")
    if problems:
        for problem in problems:
            print(f"validate_codex_package: ERROR: {problem}", file=sys.stderr)
        return None
    return marketplace, entries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-available", action="store_true")
    args = parser.parse_args(argv)
    result = validate()
    if result is None:
        return 1
    marketplace, entries = result
    print("validate_codex_package: OK")
    if args.list_available:
        print(json.dumps({
            "marketplace": marketplace["name"],
            "available": [entry["name"] for entry in entries
                          if entry["policy"]["installation"] == "AVAILABLE"],
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

