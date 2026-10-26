"""Migration preserves meaning/comments and leaves source intact on conflicts."""
import os
from pathlib import Path
import sys
import tempfile
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from split_metrics import convert, publish_new

SOURCE = """# Reviewed business definitions: preserve this comment.
metrics:
  - name: first
    definition: Eligible rows
    status: draft
    lineage: &fact
      - source: dbt
        models: [fact]
    grain: row
    expression:
      measure: COUNT(*)
      mandatory_filters: &filters
        - any_of:  # Preserve the OR, never turn it into AND.
            - {field: x, op: is_null}
            - {field: x, op: '=', value: ''}
          reason: Empty includes null and blank.
  - name: second
    definition: Eligible total
    status: draft
    lineage: *fact
    grain: row
    expression:
      measure: SUM(amount)
      mandatory_filters: *filters
"""


def run():
    try:
        import ruamel.yaml
    except ImportError:
        print("test_split_metrics: skipped (install ruamel.yaml for converter tests)")
        return False
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        domain = root / "domains/sales"
        domain.mkdir(parents=True)
        source = domain / "metrics.yaml"
        source.write_text(SOURCE)
        report = convert(domain, check=True)
        assert report["status"] == "planned"
        assert not (domain / "metrics").exists()
        calls = []
        def fail_second(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError("injected write failure")
            os.replace(src, dst)
        try:
            convert(domain, replace=fail_second)
        except OSError:
            pass
        else:
            raise AssertionError("expected injected failure")
        assert source.read_text() == SOURCE
        assert not list((domain / "metrics").glob("*.yaml"))
        report = convert(domain)
        assert not source.exists()
        assert (root / report["backup"]).read_text() == SOURCE
        assert "Reviewed business definitions" in (domain / "metrics/first.yaml").read_text()
        shared = (domain / "metrics/_shared.yaml").read_text()
        assert "any_of" in shared and "Preserve the OR" in shared
        before = {p: p.read_bytes() for p in (domain / "metrics").glob("*.yaml")}
        assert convert(domain)["status"] == "unchanged"
        assert before == {p: p.read_bytes() for p in before}
        # A source reintroduced with conflicting destinations never overwrites them.
        source.write_text(SOURCE.replace("Eligible rows", "Different meaning"))
        try:
            convert(domain)
        except ValueError as exc:
            assert "conflict" in str(exc)
        else:
            raise AssertionError("expected destination conflict")
        assert source.exists() and before == {p: p.read_bytes() for p in before}
        source.write_text(SOURCE.replace("name: second", "name: FIRST"))
        try:
            convert(domain)
        except ValueError as exc:
            assert "case-fold" in str(exc)
        else:
            raise AssertionError("expected name collision")
    print("test_split_metrics: OK")
    return True


def edge_cases():
    def fixture(directory, contents=SOURCE):
        domain = Path(directory) / "domains/sales"
        domain.mkdir(parents=True)
        source = domain / "metrics.yaml"
        source.write_text(contents)
        return domain, source
    def reject(call, text):
        try:
            call()
        except ValueError as exc:
            assert text in str(exc), str(exc)
        else:
            raise AssertionError("invalid conversion was accepted")
    for malformed in ("metrics: [\n", "metrics: []\nmetrics: []\n",
                      "metrics: &loop [*loop]\n",
                      "metrics: [{name: first, expression: []}]\n"):
        with tempfile.TemporaryDirectory() as directory:
            domain, source = fixture(directory, malformed)
            reject(lambda: convert(domain), "unsafe" if "&loop" in malformed else "invalid")
            assert source.read_text() == malformed and not (domain / "metrics").exists()
            assert not (Path(directory) / ".nodal").exists()
            result = subprocess.run([sys.executable, str(ROOT / "scripts/split_metrics.py"), str(domain)],
                                    capture_output=True, text=True)
            assert result.returncode == 1 and "Traceback" not in result.stderr
    with tempfile.TemporaryDirectory() as directory:
        domain, source = fixture(directory)
        (domain / "metrics").mkdir()
        collision = domain / "metrics/FIRST.yaml"
        collision.write_text("# existing customer file\nname: FIRST\n")
        before = collision.read_bytes()
        reject(lambda: convert(domain), "case-fold destination conflict")
        assert source.read_text() == SOURCE and collision.read_bytes() == before
    with tempfile.TemporaryDirectory() as directory:
        domain, source = fixture(directory, "# Empty domain remains valid after migration.\nmetrics: []\n")
        assert convert(domain, check=True)["metric_count"] == 0
        assert not (domain / "metrics").exists()
        result = convert(domain)
        assert result["file_count"] == 0 and not source.exists()
        assert (domain / "metrics").is_dir() and convert(domain)["status"] == "unchanged"
    with tempfile.TemporaryDirectory() as directory:
        # Same semantics, different review comments: hoist the shared values and
        # retain each metric's own comment near its generated definition.
        commented = SOURCE.replace("metrics:\n", "metrics: # Wrapper review note.\n", 1).replace(
            "lineage: *fact", "lineage: [{source: dbt, models: [fact]}] # Second lineage review."
        ).replace("mandatory_filters: *filters", "mandatory_filters:\n"
                  "        - any_of: # Second filter review.\n"
                  "            - {field: x, op: is_null}\n"
                  "            - {field: x, op: '=', value: ''}\n"
                  "          reason: Empty includes null and blank.")
        domain, source = fixture(directory, commented)
        result = convert(domain)
        first = (domain / "metrics/first.yaml").read_text()
        second = (domain / "metrics/second.yaml").read_text()
        assert "Wrapper review note" in first and "Second filter review" in second
        assert "Second lineage review" in second and "include_filters" in second
        assert (Path(directory) / result["backup"]).read_text() == commented
        # Equal existing destinations are not rewritten, including their comments.
        originals = {p: p.read_bytes() for p in (domain / "metrics").glob("*.yaml")}
        source.write_text(commented)
        convert(domain)
        assert all(path.read_bytes() == contents for path, contents in originals.items())
    with tempfile.TemporaryDirectory() as directory:
        domain, source = fixture(directory)
        calls = []
        def racing_destination(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                dst.write_text("# customer created this during conversion\n")
            publish_new(src, dst)
        try:
            convert(domain, replace=racing_destination)
            assert False
        except FileExistsError:
            pass
        assert source.read_text() == SOURCE and not calls[0].exists()
        assert "customer created" in calls[1].read_text()
    with tempfile.TemporaryDirectory() as directory:
        domain, source = fixture(directory)
        calls = []
        def racing_edit(src, dst):
            if calls:
                calls[0].write_text("# customer changed this after publication\n")
                raise OSError("injected failure")
            publish_new(src, dst)
            calls.append(dst)
        try:
            convert(domain, replace=racing_edit)
            assert False
        except OSError:
            pass
        assert source.read_text() == SOURCE and "customer changed" in calls[0].read_text()
    print("test_split_metrics edge cases: OK")


if __name__ == "__main__":
    if run():
        edge_cases()
