#!/usr/bin/env python3
"""Optional semantic warnings; all unavailable/error outcomes are nonblocking.

--revision reads context-only Git blobs with this trusted checkout's schemas and
code. Never check out/import/execute a PR revision when supplying a model key.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime.semantic_lint import lint, markdown, VERSION, MODEL
from acf_runtime.impact import snapshot
from acf_runtime.observed_review import schema_dir
from acf_runtime.verified import contained, atomic_private


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=Path.cwd())
    parser.add_argument('--revision',help='read data-only context snapshot from this Git revision')
    parser.add_argument('--model',default=MODEL)
    parser.add_argument('--out',default='.nodal/semantic-lint/report.md',help='report path under ignored .nodal/')
    parser.add_argument('--format',choices=['markdown','json'],default='markdown')
    args=parser.parse_args(argv)
    root=args.repo_root.resolve()
    try:
        if args.revision:
            with snapshot(root,args.revision) as data:
                report=lint(data,model=args.model,cache_root=root,schemas=schema_dir(root))
        else:
            report=lint(root,model=args.model)
    except Exception:
        report={'version':VERSION,'model':args.model,'status':'skipped','category':'context_or_revision_unavailable',
                'warnings':[],'comparisons':[]}
    output=markdown(report) if args.format=='markdown' else json.dumps(report,indent=2)+'\n'
    try:
        atomic_private(contained(root,args.out,'.nodal'),output.encode(),overwrite=True)
    except (OSError,ValueError):
        print('semantic_lint: local report unavailable; review stdout',file=sys.stderr)
    print(output,end='')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
