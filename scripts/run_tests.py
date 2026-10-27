#!/usr/bin/env python3
"""Run every executable tests/test_*.py file directly."""
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main():
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    if not tests:
        print("run_tests: ERROR: no tests/test_*.py files found", file=sys.stderr)
        return 1
    print("run_tests: explicit branch-test mode; governance tests separately exercise live-authority gates", flush=True)
    failures = []
    for test in tests:
        print(f"run_tests: {test.name}", flush=True)
        result = subprocess.run([sys.executable, "-B", str(test)], cwd=ROOT,
                                env={**os.environ, "ACF_BRANCH_TEST": "1"})
        if result.returncode:
            failures.append((test.name, result.returncode))
    if failures:
        for name, code in failures:
            print(f"run_tests: FAILED {name} (exit {code})", file=sys.stderr)
        return 1
    print(f"run_tests: OK — {len(tests)} test files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

