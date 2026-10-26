#!/usr/bin/env python3
"""One-time metrics.yaml conversion, with comment preservation and rollback.

Requires ruamel.yaml only for conversion. --check previews without writing.
This tool reads migration input; the ACF 0.3 runtime rejects the legacy format.
"""
import argparse
from copy import deepcopy
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import sys
import tempfile

CONTAINER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTAINER / "payload" if (CONTAINER / "payload/acf_runtime").is_dir() else CONTAINER))
from acf_runtime.expressions import MeasureParser
from acf_runtime.fragments import expand_metric
from acf_runtime.loader import normalize_dates


def plain(value):
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return normalize_dates(value)


def identity(value):
    return json.dumps(plain(value), sort_keys=True, ensure_ascii=False)


def semantic(metric):
    """Make implicit reference-only lineage explicit, without inventing a policy."""
    result = plain(metric)
    if "expression" in result and "lineage" not in result:
        parsed = MeasureParser(result["expression"]["measure"]).parse()
        if parsed.references and not parsed.has_aggregate:
            result["lineage"] = "inherit"
    return result


def comment_lines(value, recursive=True, seen=None):
    """Keep round-trip review comments even when their list is hoisted elsewhere."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return []
    seen.add(id(value))
    lines = []
    def tokens(item):
        if isinstance(item, dict):
            for child in item.values():
                tokens(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                tokens(child)
        elif hasattr(item, "value") and isinstance(item.value, str):
            lines.extend(line.strip() for line in item.value.splitlines() if line.strip().startswith("#"))
    comments = getattr(value, "ca", None)
    if comments is not None:
        tokens([comments.comment, comments.items, comments.end])
    if recursive:
        children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
        for child in children:
            lines.extend(comment_lines(child, seen=seen))
    return list(dict.fromkeys(lines))


def preserve_comments(contents, lines):
    present = {line.strip() for line in contents.decode().splitlines()}
    missing = [line for line in lines if line not in present]
    return (("\n".join(missing) + "\n").encode() if missing else b"") + contents


def publish_new(source, destination):
    # Same-filesystem staging permits atomic no-clobber creation. Leave the
    # staging link for TemporaryDirectory cleanup; never replace a racing edit.
    os.link(source, destination)


def convert(domain, check=False, replace=None):
    domain = Path(domain).resolve()
    if domain.parent.name != "domains" or not domain.is_dir():
        raise ValueError("expected an existing <context-root>/domains/<domain> directory")
    root = domain.parent.parent
    source = domain / "metrics.yaml"
    if not source.exists():
        if (domain / "metrics").is_dir():
            return {"status": "unchanged", "files": [], "backup": None}
        raise ValueError("no metrics.yaml to convert")
    if source.is_symlink():
        raise ValueError("refusing a symlink source")
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.comments import CommentedMap, CommentedSeq
        from ruamel.yaml.error import YAMLError
    except ImportError:
        raise ValueError("conversion needs comment-preserving YAML: install ruamel.yaml in your Python environment") from None
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.allow_duplicate_keys = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    def read(text):
        try:
            parsed = yaml.load(text)
            identity(parsed)  # reject cyclic/nonportable YAML before any writes
            return parsed
        except (YAMLError, RecursionError, TypeError) as exc:
            raise ValueError(f"invalid migration YAML ({type(exc).__name__}); repair the source or destination before conversion") from None
    original = source.read_bytes()
    doc = read(original.decode())
    if not isinstance(doc, dict) or set(doc) != {"metrics"} or not isinstance(doc["metrics"], list):
        raise ValueError("legacy source must be an object containing metrics: [...] only")
    names, folded = set(), set()
    metrics = []
    for item in doc["metrics"]:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name) or name.startswith("_"):
            raise ValueError(f"unsafe or reserved metric name: {name!r}")
        if name in names or name.casefold() in folded:
            raise ValueError(f"duplicate/case-fold metric name: {name}")
        names.add(name); folded.add(name.casefold())
        metric = deepcopy(item)
        if "expression" in metric and (not isinstance(metric["expression"], dict)
                or not isinstance(metric["expression"].get("measure"), str)):
            raise ValueError(f"invalid expression for {name}; expected an object with a measure string")
        normalized = semantic(metric)
        if "lineage" not in metric and normalized.get("lineage") == "inherit":
            metric["lineage"] = "inherit"
        metrics.append(metric)
    shared = CommentedMap()
    # Hoist whole lists: this cannot change the meaning of nested OR/AND groups.
    for namespace, getter in (
            ("lineage", lambda m: m.get("lineage")),
            ("parameters", lambda m: m.get("parameters")),
            ("filter_sets", lambda m: m.get("expression", {}).get("mandatory_filters"))):
        groups = {}
        for metric in metrics:
            value = getter(metric)
            if isinstance(value, list) and value:
                groups.setdefault(identity(value), []).append((metric, value))
        for serialized, referrers in sorted(groups.items()):
            if len(referrers) < 2:
                continue
            value = referrers[0][1]
            anchor = getattr(getattr(value, "anchor", None), "value", None)
            fragment = anchor if anchor and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", anchor) else namespace + "_" + hashlib.sha256(serialized.encode()).hexdigest()[:10]
            entries = shared.setdefault(namespace, CommentedMap())
            if fragment in entries:
                fragment += "_" + hashlib.sha256(serialized.encode()).hexdigest()[:10]
            entries[fragment] = (CommentedMap(filters=deepcopy(value)) if namespace == "filter_sets" else deepcopy(value))
            for metric, _ in referrers:
                if namespace == "filter_sets":
                    del metric["expression"]["mandatory_filters"]
                    metric["expression"]["include_filters"] = CommentedSeq([fragment])
                elif namespace == "parameters":
                    metric[namespace] = CommentedSeq([CommentedMap(shared=fragment)])
                else:
                    metric[namespace] = CommentedMap(shared=fragment)
    planned = {}
    def dump(value):
        out = StringIO(); yaml.dump(value, out); return out.getvalue().encode()
    for original_metric, metric in zip(doc["metrics"], metrics):
        expanded = expand_metric(plain(metric), plain(shared))
        if semantic(original_metric) != semantic(expanded):
            raise ValueError(f"semantic equivalence failed for {metric['name']}")
        planned[domain / "metrics" / (metric["name"] + ".yaml")] = preserve_comments(dump(metric), comment_lines(original_metric))
    if shared:
        planned[domain / "metrics/_shared.yaml"] = dump(shared)
    # Preserve wrapper-level commentary in the first generated file as well as backup.
    if planned:
        first = next(iter(planned))
        planned[first] = preserve_comments(planned[first],
            comment_lines(doc, recursive=False) + comment_lines(doc["metrics"], recursive=False))
    destination = domain / "metrics"
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError("metrics destination must be a real directory")
    existing_names = {}
    if destination.is_dir():
        for path in destination.iterdir():
            existing_names.setdefault(path.name.casefold(), set()).add(path.name)
    for path, contents in planned.items():
        if existing_names.get(path.name.casefold(), set()) - {path.name}:
            raise ValueError(f"case-fold destination conflict; no files changed: {path}")
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError(f"unsafe destination: {path}")
        if path.exists():
            current = read(path.read_text())
            candidate = read(contents.decode())
            if identity(current) != identity(candidate):
                raise ValueError(f"destination conflict; no files changed: {path}")
    digest = hashlib.sha256(original).hexdigest()
    backup = root / ".nodal/migrations" / f"{domain.name}-{digest[:16]}.metrics.yaml"
    if not backup.resolve().is_relative_to(root) or backup.is_symlink():
        raise ValueError("unsafe backup path")
    if backup.exists() and backup.read_bytes() != original:
        raise ValueError("backup destination conflict")
    report = {"status": "planned" if check else "converted", "files": [str(p.relative_to(root)) for p in planned],
              "metric_count": len(metrics), "file_count": len(planned),
              "backup": str(backup.relative_to(root)), "remove": str(source.relative_to(root)),
              "review": "Review 0.3 approvals, ratio policy, IR, config and dimensions before validation."}
    if check:
        return report
    replace = replace or publish_new
    created = []
    source_removed = False
    # Stage everything before any destination mutation. Backups are retained on failure.
    with tempfile.TemporaryDirectory(prefix=".split-metrics-", dir=domain) as staging:
        staged = []
        for index, (path, contents) in enumerate(planned.items()):
            temporary = Path(staging) / str(index)
            temporary.write_bytes(contents)
            staged.append((temporary, path))
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            with backup.open("xb") as handle:
                os.chmod(backup, 0o600)
                handle.write(original)
        try:
            destination.mkdir(exist_ok=True)
            for temporary, path in staged:
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    if identity(read(path.read_text())) != identity(read(temporary.read_text())):
                        raise ValueError("destination changed during conversion")
                    continue
                replace(temporary, path)
                created.append(path)
            if source.read_bytes() != original:
                raise ValueError("source changed during conversion")
            source.unlink()
            source_removed = True
        except BaseException:
            if source_removed:
                source.write_bytes(original)
            for path in reversed(created):
                # A user edit after publication belongs to the user, not rollback.
                if not path.is_symlink() and path.is_file() and path.read_bytes() == planned[path]:
                    path.unlink()
            raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(convert(args.domain, args.check), indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(f"split_metrics: ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
