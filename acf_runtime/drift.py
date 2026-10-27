"""Reviewable, revision-checked status-only drift patches and local history."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import difflib
import fcntl
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import uuid

from .loader import load_context
from .markdown import draft_pattern
from .observed_review import documents, schema_dir, schema_hash
from .verified import contained, atomic_private
from eval_harness.execution import strict_json

AREA = ".nodal/drift"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def baseline_hash(root):
    path = contained(root, ".ci/lineage-baseline.json", ".ci")
    return sha(path.read_bytes()) if path.is_file() else None


def status_edits(registry, identifiers, status="draft"):
    """Preserve comments, approval metadata, method prose and unaffected objects."""
    try:
        from ruamel.yaml import YAML
    except ImportError:
        raise ValueError("status patches require ruamel.yaml; install the migration dependencies") from None
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    grouped = {}
    for identifier in sorted(identifiers):
        node = registry.nodes.get(identifier)
        if node and "status" in node.data and node.data.get("status") != status:
            grouped.setdefault(node.path, []).append(node)
    edits = []
    for name, nodes in sorted(grouped.items()):
        path = contained(registry.root, name, ".")
        before = path.read_bytes().decode()
        if all(n.kind == "pattern" for n in nodes):
            if status != "draft":
                raise ValueError("patterns require human confirmation; no automatic promotion")
            after = before
            for node in nodes:
                after = draft_pattern(after, node.id.split("#", 1)[1])
        else:
            method = nodes[0].kind == "method"
            if method:
                lines = before.splitlines(keepends=True)
                end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
                front = "".join(lines[1:end])
                body = "".join(lines[end + 1:])
            else:
                front = before
            doc = yaml.load(front)
            if nodes[0].kind == "entity":
                names = {n.data["name"] for n in nodes}
                for entity in doc["entities"]:
                    if entity["name"] in names:
                        entity["status"] = status
            else:
                doc["status"] = status
            stream = StringIO()
            yaml.dump(doc, stream)
            rendered = stream.getvalue().replace("\n", "\r\n") if "\r\n" in before else stream.getvalue()
            after = (lines[0] + rendered + lines[end] + body) if method else rendered
        if before != after:
            edits.append({"path": name, "before": before, "after": after,
                          "before_sha256": sha(before.encode()), "after_sha256": sha(after.encode())})
    return edits


def overlay(root, contents, edits, field="after"):
    """Validate with the current trusted schemas, never copied revision code."""
    with tempfile.TemporaryDirectory(prefix="nodal-drift-preview-") as directory:
        staged = Path(directory)
        for name, raw in {**contents, **{e["path"]: e[field].encode() for e in edits}}.items():
            if not name or Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("invalid drift document path")
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        registry = load_context(staged, schemas=schema_dir(root))
        if registry.errors:
            raise ValueError("drift patch context does not validate: " + ", ".join(sorted({d.code for d in registry.errors})))
        # Callers must use this while the temporary directory exists.
        yield registry


overlay = contextmanager(overlay)


def prepare(root, impact, *, source_changes=None):
    root = Path(root).resolve()
    registry = load_context(root)
    if registry.errors:
        raise ValueError("context graph must validate before preparing status changes")
    identifiers = sorted({item["id"] for item in impact["objects"] if item["id"] in registry.nodes})
    contents = documents(root)
    edits = status_edits(registry, identifiers)
    with overlay(root, contents, edits):
        pass
    batch = sha(encoded(source_changes if source_changes is not None else impact["roots"]))[:20]
    identifier = str(uuid.uuid4())
    directory = contained(root, AREA + "/" + identifier, AREA)
    plan = {"version": 1, "id": identifier, "batch": batch, "impact": impact,
            "source_changes": source_changes, "objects": identifiers, "edits": edits,
            "context": {name: sha(raw) for name, raw in contents.items()}, "schemas": schema_hash(root),
            "baseline_sha256": baseline_hash(root),
            "previous": {key: {"path": registry.nodes[key].path, "kind": registry.nodes[key].kind,
                               "data": deepcopy(registry.nodes[key].data), "body": registry.nodes[key].body}
                         for key in identifiers},
            "created_at": datetime.now(timezone.utc).isoformat()}
    patch = "".join("".join(difflib.unified_diff(e["before"].splitlines(keepends=True),
                      e["after"].splitlines(keepends=True), fromfile="a/" + e["path"], tofile="b/" + e["path"]))
                    for e in edits)
    path = directory / "plan.json"
    atomic_private(path, encoded(plan))
    atomic_private(directory / "status.patch", patch.encode())
    return {"status": "prepared_not_applied", "plan": path.relative_to(root).as_posix(),
            "sha256": sha(encoded(plan)), "patch": (directory / "status.patch").relative_to(root).as_posix(),
            "batch": batch, "files": [e["path"] for e in edits], "snapshot_batch": impact.get("snapshot_batch", [])}


@contextmanager
def locked(root):
    path = contained(root, AREA + "/apply.lock", AREA)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        path.chmod(0o600)
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another drift application is active") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def apply(root, plan_path, digest):
    """Persist exactly status-only changes; recover interruption without overwrites."""
    root = Path(root).resolve()
    with locked(root):
        path = contained(root, plan_path, AREA)
        raw = path.read_bytes()
        if sha(raw) != digest:
            raise ValueError("drift plan digest changed; inspect a fresh preview")
        plan = strict_json(raw.decode())
        if plan["version"] != 1 or path.name != "plan.json" or str(uuid.UUID(plan["id"])) != path.parent.name:
            raise ValueError("invalid drift plan identity")
        journal_path = path.parent / "application.json"
        journal = strict_json(journal_path.read_text()) if journal_path.exists() else None
        if journal and journal.get("sha256") != digest:
            raise ValueError("application journal belongs to another plan")
        if journal and journal.get("status") == "applied":
            return {"status": "applied", "id": plan["id"], "resumed": True, "files": [e["path"] for e in plan["edits"]]}
        for other in (root / AREA).glob("*/application.json"):
            if other != journal_path and strict_json(contained(root, other.relative_to(root).as_posix(), AREA).read_text())["status"] == "applying":
                raise ValueError("resume the incomplete drift application first")
        current = documents(root)
        fingerprints = {name: sha(raw) for name, raw in current.items()}
        proposed = {e["path"]: e["after_sha256"] for e in plan["edits"]}
        if (set(fingerprints) != set(plan["context"]) or schema_hash(root) != plan["schemas"]
                or baseline_hash(root) != plan["baseline_sha256"]):
            raise ValueError("context paths, schemas or baseline changed after drift preparation")
        for name, fingerprint in fingerprints.items():
            allowed = {plan["context"][name]}
            if journal:
                allowed.add(proposed.get(name))
            if fingerprint not in allowed:
                raise ValueError("context changed after drift preparation; preserve edits and resolve before applying")
        # Reconstruct the exact before state, recompute allowed status edits and
        # verify after state. A manually altered plan cannot change business logic.
        with overlay(root, current, plan["edits"], field="before") as original:
            if status_edits(original, plan["objects"]) != plan["edits"]:
                raise ValueError("plan contains changes other than the computed status patch")
            if {name: sha(raw) for name, raw in documents(original.root).items()} != plan["context"]:
                raise ValueError("plan before-state does not match its context fingerprints")
        with overlay(root, current, plan["edits"]):
            pass
        if not journal:
            journal = {"status": "applying", "sha256": digest, "started_at": datetime.now(timezone.utc).isoformat()}
            atomic_private(journal_path, encoded(journal))
        for edit in plan["edits"]:
            destination = contained(root, edit["path"], ".")
            actual = sha(destination.read_bytes())
            if actual == edit["after_sha256"]:
                continue
            if actual != edit["before_sha256"]:
                raise ValueError("destination changed during apply; preserve it and resume after resolving the conflict")
            atomic_private(destination, edit["after"].encode(), overwrite=True)
        journal.update(status="applied", completed_at=datetime.now(timezone.utc).isoformat())
        atomic_private(journal_path, encoded(journal), overwrite=True)
        return {"status": "applied", "id": plan["id"], "files": [e["path"] for e in plan["edits"]]}


def render_impact(impact):
    lines = ["## Affected context objects", "",
             "Reporting is read-only. Status changes are not applied unless an explicit plan application succeeds.", ""]
    for item in impact["objects"]:
        chain = " → ".join(item["dependency_path"])
        models = ", ".join("/".join(m) for m in item.get("changed_models", []))
        lines.append(f"- `{item['id']}` — `{item['path']}` ({item['authored_status']}); "
                     + (models + " → " if models else "") + chain)
    lines.extend(["", "## Batched Stage 5 snapshot review", ""])
    lines.extend("- `" + key + "`" for key in impact.get("snapshot_batch", []))
    if not impact.get("snapshot_batch"):
        lines.append("No affected snapshot seeds.")
    lines.extend(["", "Methods and negative seeds require human review. Reconfirming a metric does not reconfirm its consumers.",
                  "Previously approved shape/entity seeds require a fresh passing re-grade after dependency clearance."])
    lines.extend("- " + reason for reason in impact.get("reasons", []))
    return "\n".join(lines) + "\n"
