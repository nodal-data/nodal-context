#!/usr/bin/env python3
"""Acquire configured dbt manifests without checking out or running source code.

Dispatch payloads accept base64 JSON only for configured dbt source IDs. Otherwise
read one regular Git blob from the configured GitHub repo/ref. Authentication is
customer runner configuration; an optional DBT_REPO_TOKEN is passed to Git only
through its process environment, never a URL, log, or persisted Git config.

Stdout is a JSON {source_id: absolute_manifest_path} map for drift.py
--manifest-map. Unavailable sources are omitted and reported as unchecked by drift.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime.loader import read_yaml, Schemas
from eval_harness.execution import strict_json

MAX_MANIFEST_BYTES = 64 * 1024 * 1024


def _warn(msg):
    print(f"collect_manifests: WARNING: {msg}", file=sys.stderr)


def load_sources(config_path):
    cfg = read_yaml(config_path)
    if Schemas(ROOT / "schemas").errors("config", cfg):
        raise ValueError("a valid ACF 0.3 context.config.yaml is required")
    sources = []
    seen = set()
    for source in cfg["lineage_sources"]:
        identifier = source["id"]
        if not identifier or identifier in seen:
            raise ValueError("lineage source IDs must be nonempty and unique")
        seen.add(identifier)
        sources.append({"id": identifier, "type": source["type"], "repo": source.get("repo"),
                        "ref": source.get("ref") or "main",
                        "manifest_path": source.get("manifest_path") or "target/manifest.json"})
    return sources


def validate_manifest(raw):
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds size limit")
    doc = strict_json(raw.decode("utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("nodes"), dict):
        raise ValueError("manifest must contain a nodes object")
    if "sources" in doc and not isinstance(doc["sources"], dict):
        raise ValueError("manifest sources must be an object")
    return raw


def destination(out_dir, source_id):
    # IDs never become paths or CLI syntax, including IDs with spaces or slashes.
    name = hashlib.sha256(source_id.encode()).hexdigest() + ".json"
    return Path(out_dir).resolve() / name


def save_manifest(out_dir, source_id, raw):
    validate_manifest(raw)
    target = destination(out_dir, source_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("manifest destination is a symlink")
    fd, temporary = tempfile.mkstemp(prefix=".manifest-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(target)


def from_payload(event, out_dir, allowed_ids):
    """Return acquired ID/path map. Ignore unknown IDs without writing any files."""
    acquired = {}
    payload = event.get("client_payload", {}) if isinstance(event, dict) else {}
    manifests = payload.get("manifests", {}) if isinstance(payload, dict) else {}
    if not isinstance(manifests, dict):
        _warn("payload manifests must be an object; ignoring payload")
        return acquired
    for source_id, encoded in manifests.items():
        if source_id not in allowed_ids:
            _warn("ignoring payload manifest for an unconfigured or non-dbt source")
            continue
        try:
            if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_MANIFEST_BYTES + 2) // 3):
                raise ValueError("invalid encoded manifest")
            raw = base64.b64decode(encoded, validate=True)
            acquired[source_id] = save_manifest(out_dir, source_id, raw)
        except (ValueError, TypeError, OSError):
            # Do not echo payload fragments, paths, arbitrary JSON or exception text.
            _warn(f"source {source_id!r}: invalid or unwritable payload manifest")
    return acquired


def _clone_url(repo):
    value = repo.removeprefix("https://").removeprefix("github.com/").removesuffix("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", value) or value.split("/")[1] in (".", ".."):
        raise ValueError("repo must be a GitHub owner/repository or HTTPS GitHub URL")
    return f"https://github.com/{value}.git"


def _git_env(token):
    env = os.environ.copy()
    env.pop("DBT_REPO_TOKEN", None)
    # Avoid inherited command/config injection; normal customer credential helpers
    # remain available. The only per-command config is an ephemeral auth header.
    for key in list(env):
        if key.startswith("GIT_CONFIG_"):
            env.pop(key)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if token:
        credential = base64.b64encode(("x-access-token:" + token).encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                   GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + credential)
    return env


def _manifest_path(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts or ".git" in path.parts
            or "\\" in value or any(ord(c) < 32 for c in value) or path.as_posix() != value):
        raise ValueError("manifest_path must be a normalized repo-relative file")
    return path.as_posix()


def clone_source(src, out_dir, token=""):
    """Fetch a regular blob only, with bounded size. No source checkout or execution."""
    if src["type"] != "dbt" or not src.get("repo"):
        return None
    try:
        url = _clone_url(src["repo"])
        manifest_path = _manifest_path(src["manifest_path"])
        ref = src["ref"]
        if not ref or ref.startswith("-") or any(ord(c) < 32 for c in ref):
            raise ValueError("invalid source ref")
        env = _git_env(token)
        with tempfile.TemporaryDirectory(prefix="nodal-manifest-") as directory:
            def git(*args):
                return subprocess.run(["git", *args], cwd=directory, env=env, check=True,
                                      capture_output=True, timeout=120).stdout
            git("clone", "--no-checkout", "--depth", "1", "--branch", ref, "--", url, directory)
            record = git("--literal-pathspecs", "ls-tree", "-z", "HEAD", "--", manifest_path)
            entries = record.rstrip(b"\0").split(b"\0")
            if len(entries) != 1 or b"\t" not in entries[0]:
                raise ValueError("manifest blob not found")
            metadata, name = entries[0].split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            if (mode not in ("100644", "100755") or kind != "blob"
                    or name.decode() != manifest_path or not re.fullmatch(r"[0-9a-f]{40,64}", oid)):
                raise ValueError("manifest must be a regular file, not a symlink or tree")
            size = int(git("cat-file", "-s", oid))
            if size > MAX_MANIFEST_BYTES:
                raise ValueError("manifest exceeds size limit")
            raw = git("cat-file", "blob", oid)
            return save_manifest(out_dir, src["id"], raw)
    except (OSError, ValueError, subprocess.SubprocessError):
        _warn(f"source {src['id']!r}: manifest acquisition failed; check repo/ref/path and runner access")
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="context.config.yaml")
    parser.add_argument("--out-dir", default=".nodal/manifests")
    parser.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    args = parser.parse_args(argv)
    try:
        sources = load_sources(args.config)
    except (ValueError, OSError, yaml.YAMLError):
        # YAML/schema failures are configuration errors, not missing source evidence.
        _warn("invalid context configuration; collection stopped")
        return 2
    event = {}
    if args.event_path:
        try:
            event = strict_json(Path(args.event_path).read_text())
        except (ValueError, OSError):
            _warn("could not parse event JSON; ignoring payload")
    acquired = from_payload(event, args.out_dir, {s["id"] for s in sources if s["type"] == "dbt"})
    for source in sources:
        if source["id"] not in acquired:
            path = clone_source(source, args.out_dir, os.environ.get("DBT_REPO_TOKEN", ""))
            if path:
                acquired[source["id"]] = path
    print(json.dumps(acquired, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
