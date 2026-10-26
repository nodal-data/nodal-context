"""Fresh shape/entity seed checks with unchanged approval and dependency gates.

Only seeds can be restored. No cached verdict authorizes a write. Historical
approval is read as Git data; generation never receives seed expectations.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import uuid
import yaml
from jsonschema import Draft202012Validator

from .drift import baseline_hash, encoded, sha, status_edits, overlay, locked
from .impact import commit, git
from .loader import load_context, Schemas, UniqueLoader, normalize_dates
from .observed_review import documents, schema_dir, schema_hash
from .verified import atomic_private, contained
from eval_harness import client
from eval_harness.adapters.acf import build_ncr
from eval_harness.execution import strict_json
from eval_harness.grader import grade_answer

AREA = ".nodal/regrades"


def interpretation(data):
    return {k: v for k, v in data.items() if k != "status"}


def fingerprints(root):
    return {"documents": {name: sha(raw) for name, raw in documents(root).items()},
            "schemas": schema_hash(root), "baseline": baseline_hash(root)}


def approved_history(root, seeds, reference="HEAD"):
    """Nearest stored human-confirmed seed on this path, within 100 changes.

    Do not execute any code/schema from history, follow renames, or search past a
    newer approval with a different interpretation to recover an older match.
    """
    revision = commit(root, reference)
    checker = Schemas(schema_dir(root))
    records = {}
    for node in seeds:
        revisions = [revision, *git(root, "log", "-100", "--format=%H", revision, "--", node.path).decode().splitlines()]
        for current in dict.fromkeys(revisions):
            entry = git(root, "--literal-pathspecs", "ls-tree", "-z", current, "--", node.path).rstrip(b"\0")
            if not entry:
                continue
            header, name = entry.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            if mode not in ("100644", "100755") or kind != "blob" or name.decode() != node.path:
                break
            raw = git(root, "cat-file", "blob", oid)
            try:
                value = normalize_dates(yaml.load(raw.decode(), Loader=UniqueLoader))
            except (ValueError, yaml.YAMLError):
                break
            if not isinstance(value, dict):
                break
            if value.get("status") != "confirmed":
                continue
            if not checker.errors("evalseed", value):
                records[node.id] = {"data": value, "revision": current, "blob": oid}
            break
    return records


def check_seeds(root, previous, *, seed_ids=None, model=client.MODEL, provider=client):
    """Return private evidence + sanitized report. Never mutates authored files."""
    root = Path(root).resolve()
    registry = load_context(root)
    if registry.errors:
        raise ValueError("current context must validate before re-grading")
    selected = set(seed_ids) if seed_ids is not None else {n.id for n in registry.seeds if n.data["status"] == "draft"}
    if selected - {n.id for n in registry.seeds}:
        raise ValueError("unknown re-grade seed ID")
    initial = fingerprints(root)
    ncr = build_ncr(root)
    checks = []
    available = provider.available()
    for node in sorted(registry.seeds, key=lambda n: n.id):
        if node.id not in selected:
            continue
        record = {"seed": node.id, "status": "skipped", "category": "human_review_required", "eligible": False}
        checks.append(record)
        if node.data["status"] != "draft":
            record["category"] = "already_confirmed"
            continue
        kind = node.data["expected"]["kind"]
        if kind not in ("sql_shape", "semantic_entity"):
            continue
        prior = previous.get(node.id, {})
        old = prior.get("data", {})
        if old.get("status") != "confirmed" or not old.get("approver") or not old.get("confirmed_at"):
            record["category"] = "previous_human_approval_unavailable"
            continue
        if interpretation(old) != interpretation(node.data):
            record["category"] = "authored_interpretation_changed"
            continue
        record["approval"] = deepcopy(prior)
        # Lost dimensions / unresolved targets are interpretation gaps requiring
        # human review even if a model would produce a superficially passing answer.
        if any(reason.startswith(("dimensions.seed:", "entity.unresolved:", "reference.missing:", "reference.anchor:"))
               for reason in node.local_blockers):
            record["category"] = "definition_or_dimension_review_required"
            continue
        if not available:
            record["category"] = "judge_unavailable"
            continue
        context = ncr.context_for(node.domain)
        if len(context) > client.MAX_CONTEXT_CHARS:
            record["category"] = "complete_context_exceeds_model_limit"
            continue
        method_ref = node.data.get("ir", {}).get("method")
        method = registry.resolve(method_ref, node.domain, "method") if method_ref else None
        expected = deepcopy(node.data["expected"])
        if kind == "semantic_entity":
            expected["entity_definitions"] = [registry.nodes[key].data for key in sorted(node.dependencies)
                                              if registry.nodes[key].kind == "entity"]
        attempts = []
        for question in [node.data["question"], *(v["text"] for v in node.data.get("variants", []))]:
            attempt = {"question": question, "status": "skipped", "category": "generation_unavailable"}
            attempts.append(attempt)
            try:
                answer = provider.generate(question, context_text=context, model=model)
            except Exception:
                continue
            attempt["answer"] = answer
            if not Draft202012Validator(client._GEN_SCHEMA).is_valid(answer):
                attempt["category"] = "invalid_answer_contract"
                continue
            try:
                verdict = grade_answer(expected, answer,
                    lambda evidence, obligations: provider.judge(evidence, obligations, model=model),
                    method=method.data if method else None)
            except (ValueError, TypeError, AttributeError):
                attempt["category"] = "invalid_answer_or_grade"
                continue
            attempt.update(status=verdict.status, category="graded", reason=verdict.reason, components=verdict.components)
        record["attempts"] = attempts
        statuses = {a["status"] for a in attempts}
        if "fail" in statuses:
            record.update(status="fail", category="fresh_grade_failed")
        elif statuses != {"pass"}:
            record["category"] = "fresh_checks_incomplete"
        else:
            blockers = node.blocking_reasons - {"authored_draft"}
            ready = not blockers and bool(node.dependencies) and all(
                registry.nodes[key].effective_status == "confirmed" for key in node.dependencies)
            record.update(status="pass", eligible=ready,
                          category="eligible_for_restoration" if ready else "dependency_review_pending")
    if fingerprints(root) != initial:
        raise ValueError("context changed during re-grading; fresh checks are required")
    evidence = {"version": 1, "checked_at": datetime.now(timezone.utc).isoformat(), "model": model,
                "fingerprints": initial, "checks": checks}
    report = public_report(evidence)
    return evidence, report


def public_report(evidence):
    # No generated SQL, expected values, private approval records or judge prose.
    return {"results": [{key: r[key] for key in ("seed", "status", "category", "eligible")}
                        for r in evidence["checks"]]}


def run_regrade(root, *, approved_ref="HEAD", seed_ids=None, restore=False, model=client.MODEL, provider=client):
    root = Path(root).resolve()
    registry = load_context(root)
    if registry.errors:
        raise ValueError("current context must validate before re-grading")
    previous = approved_history(root, registry.seeds, approved_ref)
    evidence, _ = check_seeds(root, previous, seed_ids=seed_ids, model=model, provider=provider)
    run_id = str(uuid.uuid4())
    directory = contained(root, AREA + "/" + run_id, AREA)
    evidence_path = directory / "evidence.json"
    evidence["application"] = "not_requested" if not restore else "pending"
    atomic_private(evidence_path, encoded(evidence))
    if restore:
        with locked(root):
            for path in (root / ".nodal/drift").glob("*/application.json"):
                journal = strict_json(contained(root, path.relative_to(root).as_posix(), ".nodal/drift").read_text())
                if journal.get("status") == "applying":
                    raise ValueError("resume the incomplete drift application before seed restoration")
            if fingerprints(root) != evidence["fingerprints"]:
                raise ValueError("context changed after re-grading; fresh checks are required")
            current = load_context(root)
            identifiers = {r["seed"] for r in evidence["checks"] if r["eligible"]}
            # The API never accepts metrics, methods, snapshots or a cached receipt
            # as candidates. Recompute seed-only status edits from this exact graph.
            edits = status_edits(current, identifiers, status="confirmed")
            contents = documents(root)
            with overlay(root, contents, edits):
                pass
            expected = deepcopy(evidence["fingerprints"])
            evidence.update(application="restoring", edits=edits)
            atomic_private(evidence_path, encoded(evidence), overwrite=True)
            for edit in edits:
                if fingerprints(root) != expected:
                    raise ValueError("context changed during restoration; preserve edits and re-grade remaining drafts")
                atomic_private(contained(root, edit["path"], "evals/seeds"), edit["after"].encode(), overwrite=True)
                expected["documents"][edit["path"]] = edit["after_sha256"]
                for record in evidence["checks"]:
                    if current.nodes[record["seed"]].path == edit["path"]:
                        record["category"] = "restored"
                atomic_private(evidence_path, encoded(evidence), overwrite=True)
            evidence["application"] = "complete"
            atomic_private(evidence_path, encoded(evidence), overwrite=True)
    report = public_report(evidence)
    report.update(run_id=run_id, evidence=evidence_path.relative_to(root).as_posix())
    atomic_private(directory / "report.json", encoded(report))
    return report
