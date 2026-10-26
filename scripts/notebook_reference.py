#!/usr/bin/env python3
"""Optional Python/nbclient reference executor for verify_notebook.py.

Requires an owner-reviewed notebook and a customer environment with read-only
data permissions. Conservative static preflight is not a sandbox. Unsupported
notebooks need review or a customer executor, never a silent preflight bypass.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE if (BASE / "acf_runtime").is_dir() else BASE / "payload"))
from eval_harness.execution import strict_json


class Blocked(ValueError):
    pass


def preflight(book):
    import sqlglot
    from sqlglot import exp
    forbidden_modules = {"os", "subprocess", "socket", "requests", "httpx", "urllib", "shutil", "ctypes", "importlib"}
    forbidden_calls = {"eval", "exec", "compile", "__import__", "system", "popen", "get_ipython",
                       "to_sql", "commit", "remove", "unlink", "rmdir", "write_text", "write_bytes",
                       "to_csv", "to_parquet", "to_pickle", "dump", "dumps_to_file", "save", "savefig"}
    for cell in book.cells:
        if cell.cell_type != "code":
            continue
        try:
            tree = ast.parse(cell.source)
        except SyntaxError as exc:
            raise Blocked("unsupported notebook magic or syntax") from exc
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                if any(name.split(".")[0] in forbidden_modules for name in modules):
                    raise Blocked("external effects require an owner-reviewed customer executor")
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                if name in forbidden_calls:
                    raise Blocked("side-effecting or dynamic operation requires review")
                if name == "open":
                    mode = next((kw.value for kw in node.keywords if kw.arg == "mode"), node.args[1] if len(node.args) > 1 else ast.Constant("r"))
                    if not isinstance(mode, ast.Constant) or mode.value not in ("r", "rb", "rt"):
                        raise Blocked("file writes require review")
                if name in ("execute", "executemany", "query", "sql", "read_sql", "read_sql_query"):
                    if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                        raise Blocked("dynamic SQL requires an owner-reviewed customer executor")
                    try:
                        statements = sqlglot.parse(node.args[0].value)
                    except sqlglot.errors.SqlglotError as exc:
                        raise Blocked("unparsed SQL requires review") from exc
                    if not statements or any(not isinstance(s, exp.Query) or s.find(exp.Into) for s in statements):
                        raise Blocked("only read-only SQL is supported")


def bind_parameters(book, parameters):
    cells = [c for c in book.cells if c.cell_type == "code" and "parameters" in c.metadata.get("tags", [])]
    if not parameters and not cells:
        return
    if len(cells) != 1:
        raise Blocked("exactly one tagged parameters cell is required for bindings")
    tree = ast.parse(cells[0].source)
    seen = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise Blocked("parameters cell must contain only simple literal assignments")
        name = node.targets[0].id
        try:
            ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError) as exc:
            raise Blocked("parameter defaults must be literals") from exc
        if name in seen:
            raise Blocked("duplicate parameter assignment")
        seen.add(name)
        if name in parameters:
            node.value = ast.parse(repr(parameters[name]), mode="eval").body
    if set(parameters) - seen:
        raise Blocked("binding is not declared in the notebook parameters cell")
    cells[0].source = ast.unparse(ast.fix_missing_locations(tree))


def execute_reference(request):
    import nbformat
    import nbclient
    import ipykernel
    from jupyter_client import AsyncKernelManager
    from jupyter_client.kernelspec import KernelSpecManager
    if request.get("role") != "reference" or request.get("require_read_only") is not True:
        raise Blocked("invalid reference request")
    path = Path(request["notebook"])
    raw = path.read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != request["source_hash"]:
        raise Blocked("notebook revision changed")
    book = nbformat.reads(raw.decode(), as_version=4)
    language = book.metadata.get("language_info", {}).get("name", "python")
    if language != "python":
        raise Blocked("built-in reference executor supports Python notebooks only")
    preflight(book)
    bind_parameters(book, request["parameters"])
    output = request["output"]
    if not isinstance(output, str) or not output.isidentifier() or output.startswith("_"):
        raise Blocked("output must name a public notebook variable containing JSON rows or a DataFrame")
    for cell in book.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    setup = "import random\nacf_inputs = " + repr(request["inputs"]) + "\n"
    if request["random_seed"] is not None:
        setup += "random.seed(" + repr(request["random_seed"]) + ")\n"
        setup += "try:\n    import numpy as np\n    np.random.seed(" + repr(request["random_seed"]) + ")\nexcept ImportError:\n    pass\n"
    book.cells.insert(0, nbformat.v4.new_code_cell(setup))
    capture = f"""import json as _acf_json
from IPython.display import display as _acf_display
_acf_output = {output}
if isinstance(_acf_output, list):
    _acf_rows = _acf_output
    _acf_columns = list(_acf_rows[0]) if _acf_rows else []
elif type(_acf_output).__module__.startswith('pandas.') and type(_acf_output).__name__ == 'DataFrame':
    _acf_columns = list(_acf_output.columns)
    _acf_rows = _acf_output.to_dict(orient='records')
else:
    raise ValueError('output must be JSON row objects or a pandas DataFrame')
_acf_payload = {{'rows': _acf_rows, 'columns': _acf_columns}}
_acf_json.dumps(_acf_payload, allow_nan=False)
_acf_display({{'application/json': _acf_payload}}, raw=True)
"""
    book.cells.append(nbformat.v4.new_code_cell(capture))
    # A task-local kernel specification avoids touching host Jupyter configuration.
    spec_root = Path.cwd() / "kernels"
    kernel_dir = spec_root / "acf-python"
    kernel_dir.mkdir(parents=True)
    (kernel_dir / "kernel.json").write_text(json.dumps({"argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "ACF reference", "language": "python", "env": {"TZ": request["timezone"], "IPYTHONDIR": str(Path.cwd() / "ipython")}}))
    class TaskKernelManager(AsyncKernelManager):
        def __init__(self, **kwargs):
            super().__init__(**kwargs, kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(spec_root)]),
                             connection_file=str(Path.cwd() / "kernel-connection.json"))
    client = nbclient.NotebookClient(book, kernel_name="acf-python", kernel_manager_class=TaskKernelManager,
                                    timeout=300, startup_timeout=20, allow_errors=False,
                                    resources={"metadata": {"path": str(Path.cwd())}})
    # Keep the kernel in this executor's process group so the orchestrator's
    # timeout terminates it as well as the executor.
    client.execute(start_new_session=False)
    nbformat.write(book, Path.cwd() / "executed.ipynb")
    payloads = [o.get("data", {}).get("application/json") for o in book.cells[-1].outputs
                if "application/json" in o.get("data", {})]
    if len(payloads) != 1:
        raise Blocked("output could not be extracted")
    return {"request_id": request["request_id"], "status": "ok", "executed": True,
            "read_only": True, "fresh_session": True, "immutable_input": True,
            "session_id": uuid.uuid4().hex, "input_fingerprint": request["input_fingerprint"],
            "context_hash": request["context_hash"], "source_hash": request["source_hash"], "as_of": request["as_of"],
            "environment": {"python": sys.version.split()[0], "nbclient": nbclient.__version__, "ipykernel": ipykernel.__version__},
            **payloads[0]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only-environment", action="store_true",
                        help="owner attests notebook reviewed and data credentials enforce read-only access")
    parser.add_argument("--immutable-input", action="store_true",
                        help="owner attests inputs identify an immutable dataset/snapshot")
    args = parser.parse_args(argv)
    request = {}
    try:
        request = strict_json(sys.stdin.read())
        if not args.read_only_environment or not args.immutable_input:
            raise Blocked("read-only environment and immutable input attestations are required")
        receipt = execute_reference(request)
    except Exception as exc:
        # No exception detail on stdout: notebook errors may contain data/credentials.
        import traceback
        diagnostic = Path.cwd() / "reference-error.txt"
        fd = os.open(diagnostic, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(traceback.format_exc())
        receipt = {"request_id": request.get("request_id"), "status": "blocked", "category": type(exc).__name__}
        print("Reference execution blocked: " + type(exc).__name__, file=sys.stderr)
    print(json.dumps(receipt, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
