#!/usr/bin/env python3
"""Validate and atomically write Nodal project-local configuration."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


CONFIG_NAME = ".nodal.local.json"
SUPPORTED_VERSION = 1
SECRET_KEY = re.compile(
    r"(^|_)(api_?key|secret|token|password|passwd|credential|private_?key|access_?key|auth)(_|$)",
    re.IGNORECASE,
)
CAPABILITY_STATUSES = {
    "read_query": {"ok", "unavailable", "denied"},
    "metadata": {"ok", "unavailable", "denied"},
    "query_history": {"full", "limited", "unavailable", "denied", "unsupported"},
}
CONTEXT_KINDS = {"acf", "ktx", "dbt", "markdown", "agent-skill", "documentation"}
CONTEXT_ACCESS = {"local", "mcp"}
CONTEXT_AUTHORITIES = {"confirmed", "governed", "documented", "behavioral", "inferred"}
CONTEXT_STATUSES = {"ok", "unavailable", "denied", "unsupported"}
BROWSER_MODES = {"ask_when_needed", "manual", "automated"}
TOP_KEYS = {"version", "warehouse", "context_sources", "browser"}


class ConfigError(ValueError):
    pass


def _object(value, label):
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be an object")
    return value


def _only_keys(value, allowed, label):
    extras = sorted(set(value) - set(allowed))
    if extras:
        raise ConfigError(f"{label} has unsupported fields: {', '.join(extras)}")


def _reject_secret_fields(value, path="config"):
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY.search(str(key)):
                raise ConfigError(f"secret-like field is forbidden: {path}.{key}")
            _reject_secret_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_fields(child, f"{path}[{index}]")


def _string_or_null(value, label):
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ConfigError(f"{label} must be a non-empty string or null")


def _verified_at(value, label):
    if not isinstance(value, str):
        raise ConfigError(f"{label} must be an ISO-8601 string")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigError(f"{label} must be an ISO-8601 string") from exc


def validate_config(config):
    """Return config after strict, secret-safe version-1 validation."""
    config = _object(config, "config")
    _reject_secret_fields(config)
    _only_keys(config, TOP_KEYS, "config")
    if config.get("version") != SUPPORTED_VERSION:
        raise ConfigError(f"version must be {SUPPORTED_VERSION}")

    warehouse = _object(config.get("warehouse"), "warehouse")
    _only_keys(warehouse, {"platform", "mcp_server", "capabilities"}, "warehouse")
    for key in ("platform", "mcp_server"):
        if not isinstance(warehouse.get(key), str) or not warehouse[key].strip():
            raise ConfigError(f"warehouse.{key} must be a non-empty string")
    capabilities = _object(warehouse.get("capabilities"), "warehouse.capabilities")
    _only_keys(capabilities, CAPABILITY_STATUSES, "warehouse.capabilities")
    for name, statuses in CAPABILITY_STATUSES.items():
        capability = _object(capabilities.get(name), f"warehouse.capabilities.{name}")
        _only_keys(capability, {"status", "verified_at"}, f"warehouse.capabilities.{name}")
        if capability.get("status") not in statuses:
            raise ConfigError(
                f"warehouse.capabilities.{name}.status must be one of {', '.join(sorted(statuses))}"
            )
        _verified_at(capability.get("verified_at"), f"warehouse.capabilities.{name}.verified_at")

    sources = config.get("context_sources")
    if not isinstance(sources, list):
        raise ConfigError("context_sources must be an array")
    names = set()
    for index, raw_source in enumerate(sources):
        label = f"context_sources[{index}]"
        source = _object(raw_source, label)
        _only_keys(
            source,
            {
                "name",
                "kind",
                "access",
                "location",
                "binding",
                "repo",
                "authority",
                "status",
                "verified_at",
                "enabled",
            },
            label,
        )
        name = source.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"{label}.name must be a non-empty string")
        if name in names:
            raise ConfigError(f"context source name must be unique: {name}")
        names.add(name)
        if source.get("kind") not in CONTEXT_KINDS:
            raise ConfigError(f"{label}.kind must be one of {', '.join(sorted(CONTEXT_KINDS))}")
        access = source.get("access")
        if access not in CONTEXT_ACCESS:
            raise ConfigError(f"{label}.access must be one of {', '.join(sorted(CONTEXT_ACCESS))}")
        for field in ("location", "binding", "repo"):
            _string_or_null(source.get(field), f"{label}.{field}")
        if access == "local" and not source.get("location"):
            raise ConfigError(f"{label}.location is required for local access")
        if access == "local" and source.get("binding") is not None:
            raise ConfigError(f"{label}.binding must be null for local access")
        if access == "mcp" and not source.get("binding"):
            raise ConfigError(f"{label}.binding is required for MCP access")
        if access == "mcp" and source.get("location") is not None:
            raise ConfigError(f"{label}.location must be null for MCP access")
        if source.get("authority") not in CONTEXT_AUTHORITIES:
            raise ConfigError(
                f"{label}.authority must be one of {', '.join(sorted(CONTEXT_AUTHORITIES))}"
            )
        if source.get("status") not in CONTEXT_STATUSES:
            raise ConfigError(f"{label}.status must be one of {', '.join(sorted(CONTEXT_STATUSES))}")
        _verified_at(source.get("verified_at"), f"{label}.verified_at")
        if not isinstance(source.get("enabled"), bool):
            raise ConfigError(f"{label}.enabled must be a boolean")

    browser = _object(config.get("browser"), "browser")
    _only_keys(browser, {"mode", "binding"}, "browser")
    _string_or_null(browser.get("binding"), "browser.binding")
    mode = browser.get("mode")
    if mode is not None and mode not in BROWSER_MODES:
        raise ConfigError(f"browser.mode must be one of {', '.join(sorted(BROWSER_MODES))}")
    effective_mode = mode or ("automated" if browser.get("binding") else "ask_when_needed")
    if effective_mode == "automated" and not browser.get("binding"):
        raise ConfigError("browser.binding is required when browser.mode is automated")
    if effective_mode != "automated" and browser.get("binding") is not None:
        raise ConfigError("browser.binding must be null unless browser.mode is automated")
    return config


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"malformed JSON in {path}: line {exc.lineno}, column {exc.colno}") from exc


def _git_root(start):
    result = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else None


def discover_config(start):
    """Find the nearest config, stopping at the containing git root when present."""
    current = Path(start).expanduser().resolve()
    if current.is_file():
        current = current.parent
    boundary = _git_root(current)
    while True:
        candidate = current / CONFIG_NAME
        if candidate.is_file():
            validate_config(load_json(candidate))
            return candidate
        if current == boundary or current.parent == current:
            return None
        current = current.parent


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_config(project_root, input_path):
    destination = Path(project_root).expanduser().resolve() / CONFIG_NAME
    if destination.exists():
        validate_config(load_json(destination))
    config = validate_config(load_json(Path(input_path).expanduser().resolve()))
    atomic_write(destination, config)
    return destination


def mcp_binding_status(project_root, binding):
    """Return a sanitized project binding status without exposing MCP configuration."""
    destination = Path(project_root).expanduser().resolve() / ".mcp.json"
    if not destination.exists():
        return "absent"
    current = _object(load_json(destination), ".mcp.json")
    servers = current.get("mcpServers", {})
    _object(servers, ".mcp.json.mcpServers")
    return "configured" if binding in servers else "absent"


def merge_mcp(project_root, binding, consent=False):
    if not consent:
        raise ConfigError("browser MCP merge requires explicit --consent")
    if binding != "chrome-devtools":
        raise ConfigError("only the bundled chrome-devtools binding is supported")
    skill_root = Path(__file__).resolve().parents[1]
    template = load_json(skill_root / "assets" / "chrome-devtools.mcp.json")
    addition = _object(template.get("mcpServers"), "template.mcpServers")[binding]
    destination = Path(project_root).expanduser().resolve() / ".mcp.json"
    if destination.exists():
        current = _object(load_json(destination), ".mcp.json")
    else:
        current = {}
    servers = current.setdefault("mcpServers", {})
    _object(servers, ".mcp.json.mcpServers")
    if binding in servers:
        raise ConfigError(f"browser binding already exists; refusing to overwrite: {binding}")
    servers[binding] = addition
    atomic_write(destination, current)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    discover = subparsers.add_parser("discover")
    discover.add_argument("--start", default=".")
    validate = subparsers.add_parser("validate")
    validate.add_argument("path")
    write = subparsers.add_parser("write")
    write.add_argument("--project-root", required=True)
    write.add_argument("--input", required=True)
    mcp_status = subparsers.add_parser("mcp-status")
    mcp_status.add_argument("--project-root", required=True)
    mcp_status.add_argument("--binding", required=True)
    merge = subparsers.add_parser("merge-mcp")
    merge.add_argument("--project-root", required=True)
    merge.add_argument("--binding", required=True)
    merge.add_argument("--consent", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "discover":
            found = discover_config(args.start)
            print(found or "")
        elif args.command == "validate":
            validate_config(load_json(Path(args.path).expanduser().resolve()))
            print(f"nodal_config: OK — {args.path}")
        elif args.command == "write":
            print(f"nodal_config: wrote {write_config(args.project_root, args.input)}")
        elif args.command == "mcp-status":
            print(mcp_binding_status(args.project_root, args.binding))
        else:
            print(f"nodal_config: wrote {merge_mcp(args.project_root, args.binding, args.consent)}")
    except ConfigError as exc:
        print(f"nodal_config: ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
