"""Offline test for .ci/collect_manifests.py — stdlib only, no pytest, no network.

Covers the parts that don't shell out: dispatch-payload decoding (valid + garbage)
and authenticated clone-URL construction. The git-clone path is integration glue and
is not exercised here.

Run: python3 tests/test_collect_manifests.py   (exit 0 = pass)
"""
import base64
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".ci"))
import collect_manifests as cm  # noqa: E402


def run():
    # --- from_payload: valid base64 JSON is written, garbage is skipped --------
    good = base64.b64encode(json.dumps({"nodes": {}}).encode()).decode()
    event = {"client_payload": {"manifests": {"dbt_core": good, "broken": "!!notb64"}}}
    with tempfile.TemporaryDirectory() as td:
        acquired = cm.from_payload(event, td)
        assert acquired == {"dbt_core"}, acquired
        written = json.loads((Path(td) / "dbt_core.json").read_text())
        assert written == {"nodes": {}}, written
        assert not (Path(td) / "broken.json").exists()

    # --- from_payload tolerates an empty / missing payload ---------------------
    assert cm.from_payload({}, ".") == set()
    assert cm.from_payload({"client_payload": {}}, ".") == set()

    # --- clone URL: normalizes repo forms and injects the token ----------------
    assert cm._clone_url("github.com/acme/acme-dbt", "TOK") == \
        "https://x-access-token:TOK@github.com/acme/acme-dbt.git"
    assert cm._clone_url("acme/acme-dbt", "TOK") == \
        "https://x-access-token:TOK@github.com/acme/acme-dbt.git"
    assert cm._clone_url("https://github.com/acme/acme-dbt", "") == \
        "https://github.com/acme/acme-dbt.git"

    print("test_collect_manifests: OK")


if __name__ == "__main__":
    run()
