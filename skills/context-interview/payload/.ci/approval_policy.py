#!/usr/bin/env python3
"""PR-safe approval policy: no authored approval fields on new definitions."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acf_runtime.loader import load_context


def main():
    roots = [Path('.')] if Path('context.config.yaml').is_file() else sorted(Path('examples').glob('*'))
    failures = []
    for root in roots:
        if not (root/'context.config.yaml').is_file():
            continue
        registry = load_context(root, branch_test=True)
        failures.extend(str(e) for e in registry.errors)
        for node in registry.nodes.values():
            if node.kind != 'pattern' and 'status' in node.data:
                failures.append(f'{root}/{node.path}: migrate legacy status to review_history before merge')
    print('\n'.join(failures) if failures else 'approval-policy: proposed definitions only; merge authority checked separately')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
