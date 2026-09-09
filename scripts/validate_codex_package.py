#!/usr/bin/env python3
"""Validate the Codex manifest/marketplace paths and list available plugins."""
import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PORTABLE_MANIFEST_PATH = ROOT / "plugin.json"
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
    portable = load(PORTABLE_MANIFEST_PATH)
    manifest = load(MANIFEST_PATH)
    for key in ("name", "version", "description", "author", "license", "skills", "interface"):
        if key not in manifest:
            problems.append(f"manifest missing {key}")
    if not SEMVER.match(str(manifest.get("version", ""))):
        problems.append("manifest version is not strict semver")
    if manifest.get("license") != "Apache-2.0":
        problems.append("manifest license must be Apache-2.0")
    if portable.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
        problems.append("portable manifest has the wrong Agent Plugins schema")
    for key in ("name", "version", "description", "author", "license"):
        if key not in portable:
            problems.append(f"portable manifest missing {key}")
    if portable.get("name") != manifest.get("name"):
        problems.append("portable/Codex manifest name mismatch")
    if portable.get("version") != manifest.get("version"):
        problems.append("portable/Codex manifest version mismatch")
    if portable.get("license") != "Apache-2.0":
        problems.append("portable manifest license must be Apache-2.0")
    if "mcpServers" in portable or (ROOT / "mcp.json").exists():
        problems.append("portable plugin must not bundle an MCP server")
    if "mcpServers" in manifest:
        problems.append("manifest must not bundle an MCP server")
    skill_path = (ROOT / str(manifest.get("skills", ""))).resolve()
    if skill_path != (ROOT / "skills").resolve() or not skill_path.is_dir():
        problems.append("manifest skills path must resolve to root skills/")

    interface = portable.get("extensions", {}).get("com.openai", {}).get("interface", {})
    for key in (
        "displayName", "shortDescription", "longDescription", "developerName",
        "category", "websiteURL", "privacyPolicyURL", "termsOfServiceURL",
        "defaultPrompt", "brandColor", "composerIcon", "logo",
    ):
        if key not in interface:
            problems.append(f"portable OpenAI interface missing {key}")
    prompts = interface.get("defaultPrompt")
    if not isinstance(prompts, list) or not prompts or len(prompts) > 3:
        problems.append("portable OpenAI interface must have 1-3 starter prompts")
    for key in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        if not str(interface.get(key, "")).startswith("https://"):
            problems.append(f"portable OpenAI interface {key} must use https")
    for key in ("composerIcon", "logo"):
        raw_path = interface.get(key)
        if not isinstance(raw_path, str) or not raw_path.startswith("./assets/"):
            problems.append(f"portable OpenAI interface {key} must be under ./assets/")
        elif not (ROOT / raw_path).is_file():
            problems.append(f"portable OpenAI interface {key} does not exist")

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
