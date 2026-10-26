"""Checked publication payloads plus injected GitHub API lifecycle tests."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.ci')]
from test_drift_patches import setup, reject
from acf_runtime.drift import prepare, encoded
from acf_runtime.impact import lineage_impact
from acf_runtime.loader import load_context
from prepare_drift_publication import prepare_publication
from test_regrade import Provider


def run():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); setup(root)
        def git(*args):
            return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True).stdout.decode().strip()
        git('init', '-b', 'main')
        git('config', 'user.name', 'Synthetic Test')
        git('config', 'user.email', 'synthetic@example.invalid')
        git('add', '.')
        git('commit', '-m', 'synthetic context fixture')
        original = {p: p.read_bytes() for p in root.rglob('*') if p.is_file() and '.git' not in p.parts}
        impact = lineage_impact(load_context(root), {('dbt', 'orders')})
        plan = prepare(root, impact)
        report = {'impact': impact, 'patch': plan, 'unchecked_sources': ['missing']}
        target = root / '.nodal/drift-report.json'; target.write_bytes(encoded(report))
        result = prepare_publication(root, '.nodal/drift-report.json', 'main')
        assert result['baseSha'] == git('rev-parse', 'HEAD')
        assert result['batch'] == plan['batch']
        assert result['edits'] and 'seed:snapshot.seed.yaml' in result['report']
        assert 'missing' in result['report']
        assert '+status: draft' in result['patch']
        assert set(result) == {'version', 'baseRef', 'baseSha', 'edits', 'batch', 'report', 'patch'}
        assert not any(e['path'].startswith('.nodal') or e['path'] == '.ci/lineage-baseline.json' for e in result['edits'])
        assert all(p.read_bytes() == raw for p, raw in original.items())
        assert (root / '.nodal/drift-publication/publication.json').stat().st_mode & 0o777 == 0o600
        # Workflow grades against the proposed draft graph, so a passing shape
        # check cannot cancel the required upstream definition review.
        checked = prepare_publication(root, '.nodal/drift-report.json', 'main', regrade=True, provider=Provider())
        assert checked['edits'] == result['edits']
        assert 're-grade passed; dependency review pending' in checked['report']
        assert 'synthetic verdict' not in checked['report']
        metric = root / 'domains/sales/metrics/orders.yaml'
        metric.write_text(metric.read_text() + '\n# human edit\n')
        reject(lambda: prepare_publication(root, '.nodal/drift-report.json', 'main'), 'changed')
        # Even a newly regenerated valid plan cannot publish uncommitted context.
        report['patch'] = prepare(root, lineage_impact(load_context(root), {('dbt', 'orders')}))
        target.write_bytes(encoded(report))
        reject(lambda: prepare_publication(root, '.nodal/drift-report.json', 'main'), 'checked-out commit')
        target.write_bytes(encoded({'impact': impact, 'unchecked_sources': ['missing']}))
        result = prepare_publication(root, '.nodal/drift-report.json', 'main')
        assert result['batch'] == 'unchecked' and result['edits'] == [] and result['patch'] == ''
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        from test_regrade import setup as setup_regrade, save
        setup_regrade(root)
        save(root)  # default branch now has stale seeds with their prior approval in history
        report = {'impact': {'objects': [], 'snapshot_batch': [], 'reasons': []}, 'unchecked_sources': []}
        target = root / '.nodal/drift-report.json'; target.parent.mkdir(); target.write_bytes(encoded(report))
        before = {p:p.read_bytes() for p in (root/'evals/seeds').glob('*.yaml')}
        result = prepare_publication(root, '.nodal/drift-report.json', 'main', regrade=True, provider=Provider())
        assert result['purpose'] == 'seed-regrade'
        assert {e['path'] for e in result['edits']} == {'evals/seeds/orders.seed.yaml','evals/seeds/customer.seed.yaml'}
        assert all('status: confirmed' in e['content'] for e in result['edits'])
        assert all(p.read_bytes() == raw for p,raw in before.items())
        result = prepare_publication(root, '.nodal/drift-report.json', 'main', regrade=True, provider=Provider(available=False))
        assert result['edits'] == [] and 'judge_unavailable' in result['report']
    subprocess.run(['node', str(ROOT / 'tests/fixtures/drift_publication.cjs')], check=True)
    print('test_drift_publication: OK')


if __name__ == '__main__':
    run()
