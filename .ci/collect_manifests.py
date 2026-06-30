#!/usr/bin/env python3
"""Collect each lineage source's dbt manifest for .ci/drift.py, in CI.

Two acquisition mechanisms, tried in order per source:
  1. repository_dispatch payload — the dbt repo's CI pushes manifests inline as
     client_payload.manifests = {source_id: "<base64 of manifest.json>"}. This is the
     proactive "lineage-changed" path (the dbt repo already parsed its manifest).
  2. clone — read the source's repo/ref/manifest_path from context.config.yaml, shallow
     `git clone` it with $DBT_REPO_TOKEN, and copy the committed manifest out.

Manifests are written to <out-dir>/<source_id>.json and the matching
`--manifest source_id=path` flags are printed to stdout for drift.py to consume.
A source we cannot acquire is WARNED, not fatal — drift.py then reports it as an
unchecked source so the gap is visible rather than silently passing.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _warn(msg):
    print(f"collect_manifests: WARNING: {msg}", file=sys.stderr)


def load_sources(config_path):
    """[(id, type, repo, ref, manifest_path), ...] from context.config.yaml."""
    import yaml
    cfg = yaml.safe_load(Path(config_path).read_text()) or {}
    out = []
    for s in cfg.get("lineage_sources") or []:
        if not s.get("id"):
            continue
        out.append({
            "id": s["id"],
            "type": s.get("type"),
            "repo": s.get("repo"),
            "ref": s.get("ref") or "main",
            "manifest_path": s.get("manifest_path") or "target/manifest.json",
        })
    return out


def from_payload(event, out_dir):
    """Decode client_payload.manifests into out_dir. Returns set of acquired ids."""
    acquired = set()
    manifests = (((event or {}).get("client_payload") or {}).get("manifests")) or {}
    for source_id, b64 in manifests.items():
        try:
            raw = base64.b64decode(b64)
            json.loads(raw)  # validate it's JSON before trusting it
        except (ValueError, TypeError) as e:
            _warn(f"payload manifest for {source_id!r} is not valid base64 JSON: {e}")
            continue
        dest = Path(out_dir) / f"{source_id}.json"
        dest.write_bytes(raw)
        acquired.add(source_id)
    return acquired


def _clone_url(repo, token):
    """github.com/org/repo -> authenticated https clone URL."""
    repo = repo.replace("https://", "").replace("http://", "").rstrip("/")
    if not repo.startswith("github.com/"):
        repo = "github.com/" + repo
    return f"https://x-access-token:{token}@{repo}.git" if token else f"https://{repo}.git"


def clone_source(src, out_dir, token):
    """Shallow-clone one dbt source and copy its committed manifest. True on success."""
    if src["type"] != "dbt" or not src["repo"]:
        return False
    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", src["ref"],
                 _clone_url(src["repo"], token), td],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            _warn(f"clone of {src['id']} ({src['repo']}@{src['ref']}) failed: "
                  f"{e.stderr.strip().splitlines()[-1] if e.stderr else e}")
            return False
        manifest = Path(td) / src["manifest_path"]
        if not manifest.exists():
            _warn(f"{src['id']}: {src['manifest_path']} not found in repo (have the dbt "
                  "CI commit it, or push it via the dispatch payload)")
            return False
        (Path(out_dir) / f"{src['id']}.json").write_text(manifest.read_text())
        return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="context.config.yaml")
    ap.add_argument("--out-dir", default=".manifests")
    ap.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("DBT_REPO_TOKEN", "")

    event = {}
    if args.event_path and Path(args.event_path).exists():
        try:
            event = json.loads(Path(args.event_path).read_text())
        except ValueError:
            _warn("could not parse GITHUB_EVENT_PATH; ignoring payload")

    acquired = from_payload(event, out_dir)

    flags = []
    for src in load_sources(args.config):
        if src["id"] in acquired or clone_source(src, out_dir, token):
            flags.append(f"--manifest {src['id']}={out_dir / (src['id'] + '.json')}")
    print(" ".join(flags))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
