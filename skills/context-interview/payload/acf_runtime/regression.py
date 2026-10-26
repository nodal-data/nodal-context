"""ACF selection/decryption adapter for the format-neutral regression executor."""
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

from .loader import load_context
from .verified import VerifiedSQL, VerificationError, contained
from eval_harness.execution import digest, private_json, validate_command
from eval_harness.regression import execute_seed


def seed_fingerprint(registry, seed):
    selected, pending = {}, [seed.id]
    while pending:
        key = pending.pop()
        if key in selected:
            continue
        node = registry.nodes[key]
        selected[key] = {"data": node.data, "body": node.body}
        pending.extend(k for k in node.dependencies if k in registry.nodes)
    return digest({"definitions": selected, "config": registry.config})


def run_regression(root, *, executor=None, judge=None, identity=None, seed_ids=None,
                   parameters=None, timeout=600, executables=None, branch_test=None):
    validate_command(executor); validate_command(judge)
    root = Path(root).resolve()
    registry = load_context(root, branch_test=branch_test)
    if registry.errors:
        raise VerificationError("invalid_context")
    manager = VerifiedSQL(root, config=registry.config, identity=identity, executables=executables)
    selected = list(registry.seeds)
    if seed_ids:
        wanted = {"seed:" + s.removeprefix("seed:").removeprefix("evals/seeds/") for s in seed_ids}
        selected = [s for s in selected if s.id in wanted]
        if {s.id for s in selected} != wanted:
            raise VerificationError("unknown_seed_selection")
    if not isinstance(parameters or {}, dict) or any(not isinstance(v, dict) for v in (parameters or {}).values()):
        raise VerificationError("parameters_must_map_seed_ids_to_binding_objects")
    if set(parameters or {}) - {s.id for s in selected}:
        raise VerificationError("parameters_reference_unselected_seed")
    run_id = uuid.uuid4().hex
    directory = contained(root, ".nodal/regressions/" + run_id)
    directory.mkdir(mode=0o700, parents=True)
    source_warehouses = {s["id"]: s.get("warehouse", registry.config["warehouse"])
                         for s in registry.config["lineage_sources"]}
    public, evidence = [], {}
    for index, node in enumerate(selected):
        seed = {**node.data, "id": node.id}
        entry = {"seed_id": node.id, "status": "skipped", "category": "no_verified_query"}
        query = node.data.get("verified_query_file")
        fingerprint = seed_fingerprint(registry, node)
        if node.effective_status != "confirmed":
            entry["category"] = "seed_draft_or_blocked"
        elif seed["expected"]["kind"] == "negative":
            entry["category"] = "negative_seed_requires_answer_evaluation"
        elif not query:
            pass
        elif not executor:
            entry["category"] = "executor_unconfigured"
        else:
            warehouses = {source_warehouses[source] for source, _ in node.lineage} or {registry.config["warehouse"]}
            if len(warehouses) != 1:
                entry["category"] = "cross_warehouse_unsupported"
                public.append(entry)
                continue
            method = None
            ir = node.data.get("ir", {})
            target = registry.resolve(ir.get("method") or ir.get("metric", ""), node.domain,
                                      "method" if ir.get("method") else "metric")
            declarations = target.data.get("parameters", []) if target else []
            bindings = {p["name"]: p["default"] for p in declarations if "default" in p}
            bindings.update(ir.get("parameters", {}))
            bindings.update((parameters or {}).get(node.id, {}))
            if set(bindings) != {p["name"] for p in declarations} or re.search(r"<[A-Za-z_]\w*>", str(bindings)):
                entry["category"] = "parameter_bindings_unresolved"
                public.append(entry)
                continue
            if target and target.kind == "method":
                method = target.data
            try:
                _, ciphertext, _ = manager.paths(query)
                artifact = ciphertext if manager.backend != "none" else root / query
                artifact_hash = digest(artifact.read_bytes().hex())
                with manager.temporary_plaintext(query) as plaintext:
                    result, details = execute_seed(seed, plaintext, next(iter(warehouses)), bindings,
                        directory / ("seed-" + str(index)), executor=executor, judge=judge, method=method, timeout=timeout)
                    entry.update(result)
                    if digest(artifact.read_bytes().hex()) != artifact_hash:
                        entry.update(status="skipped", category="query_changed_during_run")
                    evidence[node.id] = {"fingerprint": fingerprint, "artifact_hash": artifact_hash,
                                         "status": entry["status"], "checked_at": datetime.now(timezone.utc).isoformat(), **details}
            except VerificationError as exc:
                entry["category"] = exc.category
            except OSError:
                entry["category"] = "execution_io_unavailable"
        public.append(entry)
    # Changes during the run invalidate result claims, even when the old rows matched.
    current = load_context(root, branch_test=branch_test)
    for entry in public:
        item = evidence.get(entry["seed_id"])
        current_seed = current.nodes.get(entry["seed_id"])
        if item and (current.errors or not current_seed or seed_fingerprint(current, current_seed) != item["fingerprint"]):
            entry.update(status="skipped", category="context_changed_during_run")
            item["status"] = "skipped"
    private_json(directory / "evidence.json", evidence)
    report = {"schema_version": 1, "results": public, "governance": registry.governance}
    private_json(directory / "public.json", report)
    return directory, report
