#!/usr/bin/env python3
"""Convert legacy approval fields to history; requires explicit legacy admission.

This operation never publishes an authority approval. The resulting revision
must still pass protected review/merge and live freshness checks.
"""
import argparse
from io import StringIO
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT if (ROOT / 'acf_runtime').is_dir() else ROOT / 'payload'))
from acf_runtime.loader import discover_docs


def convert(root, *, admit_legacy=False):
    from ruamel.yaml import YAML
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    changes = []
    for path, kind in discover_docs(root, templates=True):
        if kind not in ('metric', 'method', 'domain', 'entity', 'evalseed'):
            continue
        before = path.read_text()
        lines = before.splitlines(keepends=True)
        end = lines.index('---\n', 1) if kind == 'method' else None
        doc = yaml.load(''.join(lines[1:end]) if kind == 'method' else before)
        objects = doc['entities'] if kind == 'entity' else [doc]
        changed = False
        for item in objects:
            history = {key: item[key] for key in ('status', 'approver', 'confirmed_at') if key in item}
            if not history:
                continue
            if history.get('status') == 'draft' and not admit_legacy:
                raise ValueError('legacy draft requires --admit-legacy or exclusion onto a working branch')
            item.setdefault('review_history', []).append(history)
            for key in history:
                del item[key]
            changed = True
        if changed:
            stream = StringIO(); yaml.dump(doc, stream)
            after = '---\n' + stream.getvalue() + ''.join(lines[end:]) if kind == 'method' else stream.getvalue()
            changes.append((path, before, after))
    # Validate all admission decisions before the first mutation; never overwrite backups.
    for path, _, _ in changes:
        if path.with_name(path.name+'.approval-backup').exists():
            raise ValueError('migration backup already exists')
    for path, before, after in changes:
        path.with_name(path.name+'.approval-backup').write_text(before)
        path.write_text(after)
    return [str(p) for p, _, _ in changes]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--admit-legacy', action='store_true', help='explicit authorization to include existing drafts in the reviewed migration')
    args = parser.parse_args()
    try:
        from acf_runtime.governance import require_working_branch
        from acf_runtime.loader import read_yaml
        config = read_yaml(args.root / 'context.config.yaml')
        require_working_branch(args.root, config.get('approval_branch', 'main'))
        print('\n'.join(convert(args.root, admit_legacy=args.admit_legacy)))
        return 0
    except (ValueError, OSError) as exc:
        print(f'migrate_approval: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
