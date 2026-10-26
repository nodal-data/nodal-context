"""Approval is live revision evidence; stale blocks survive unrelated merges."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime import load_context
from acf_runtime.governance import append_event, digest, context_files, validate_ledger
from scripts.migrate_approval import convert
from acf_fixtures import context, metric, method, seed, write, METHOD_BODY


def run():
    now = datetime.now(timezone.utc)
    checked = now.isoformat()
    expires = (now + timedelta(hours=1)).isoformat()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        context(root)
        write(root, 'domains/sales/metrics/orders.yaml', metric(status='draft'))
        write(root, 'methods/repeat.md', method(), METHOD_BODY)
        write(root, 'evals/seeds/orders.seed.yaml', seed())
        try:
            convert(root)
            raise AssertionError('unreviewed draft admitted without explicit authorization')
        except ValueError:
            pass
        assert 'status: draft' in (root/'domains/sales/metrics/orders.yaml').read_text()
        convert(root, admit_legacy=True)
        for p in root.rglob('*.approval-backup'):
            p.unlink()
        proposed = load_context(root, branch_test=True)
        assert not proposed.errors, proposed.errors
        assert all(n.approval_state == 'proposed' for n in proposed.nodes.values())
        assert proposed.governance['approved'] is False
        assert proposed.metrics[0].data['review_history'][0]['status'] == 'draft'
        missing = load_context(root, branch_test=False, authority=lambda _: {})
        assert all(n.blocking_reasons for n in missing.nodes.values())
        for args in (['init','-q'], ['add','.'], ['-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture']):
            subprocess.run(['git','-C',td,*args],check=True,capture_output=True)
        rev = subprocess.check_output(['git','-C',td,'rev-parse','HEAD'],text=True).strip()
        content = digest(context_files(root))
        def approve(events, revision=rev):
            return append_event(events,'approve',revision=revision,content_digest=content,branch='main',
                                review=['human review evidence'],checks=['passing required checks'],protection='enforced')
        events = approve([])
        def authority(request):
            return {'version':1,'nonce':request['nonce'],'approval_branch':'main','checked_at':checked,
                    'expires_at':expires,'events':deepcopy(events),'freshness':{
                        'revision':request['revision'],'content_digest':content,'checked_at':checked,'expires_at':expires,
                        'sources':{'dbt':{'status':'checked','revision':'source-1','digest':'source-hash'}}}}
        def load():
            return load_context(root,branch_test=False,authority=authority)
        approved = load()
        assert approved.governance['approved'] and not any(n.blocking_reasons for n in approved.nodes.values())
        assert all(n.approval_state == 'approved' for n in approved.nodes.values())
        # Source change revokes before any context repair file changes.
        events = append_event(events,'block',targets=['metric:sales.orders'],reason='orders source changed',
                              source_evidence={'source':'dbt','revision':'source-2'},revision=rev)
        block = events[-1]['id']
        stale = load()
        assert stale.metrics[0].blocking_reasons
        assert stale.methods[0].blocking_reasons and stale.seeds[0].blocking_reasons
        # An unrelated approval cannot erase the block, nor can a forged clear.
        events = approve(events,'b'*40)
        assert load().methods[0].blocking_reasons
        for bad in ({'revision':'c'*40,'source_evidence':{'source':'dbt','revision':'source-2'}},
                    {'revision':rev,'source_evidence':{'source':'dbt','revision':'wrong'}}):
            try:
                append_event(events,'clear',block=block,reason='repair',checks=['pass'],**bad)
                raise AssertionError('invalid clearance accepted')
            except ValueError:
                pass
        # Clearance only applies to the named reviewed revision; old revisions stay blocked.
        events = append_event(events,'clear',block=block,revision='b'*40,reason='reviewed repair',checks=['fresh pass'],
                              source_evidence={'source':'dbt','revision':'source-2'})
        assert load().metrics[0].blocking_reasons
        events = append_event(events,'clear',block=block,revision=rev,reason='reviewed repair at exact revision',
                              checks=['fresh pass'],source_evidence={'source':'dbt','revision':'source-2'})
        assert not load().methods[0].blocking_reasons
        _, blocks = validate_ledger(events)
        assert blocks[block]['reason'] == 'orders source changed'
        # Expiry, missing source evidence, response replay and local edits fail closed.
        base_authority = authority
        for mutate in (lambda r:r.update(expires_at=checked),
                       lambda r:r['freshness'].update(sources={}),
                       lambda r:r.update(nonce='replayed'),
                       lambda r:r['freshness'].update(revision='wrong'),
                       lambda r:r['events'][0].update(review=[])):
            def invalid(request):
                response=base_authority(request);mutate(response);return response
            result=load_context(root,branch_test=False,authority=invalid)
            assert all(n.blocking_reasons for n in result.nodes.values())
        (root/'company').mkdir()
        (root/'company/overview.md').write_text('unreviewed prose')
        assert load().metrics[0].blocking_reasons
        # Branch testing still cannot assert approval or clear authority events.
        test = load_context(root,branch_test=True)
        assert test.governance['mode']=='branch-test' and not test.governance['approved']
        assert len(events)==5
        (root/'company/overview.md').unlink()
        from scripts.compile_skill import compile_skill, verify_export
        from eval_harness.adapters.acf import build_ncr
        # Exports are verified by recompiling the live-approved source, not by
        # trusting a copied JSON proof. Branch-test exports cannot pass this gate.
        with patch.dict('os.environ', {'ACF_BRANCH_TEST':'0'}), patch('acf_runtime.governance.read_authority', side_effect=authority):
            export, _ = compile_skill(root, root/'dist', None, False)
            assert verify_export(root, export)['approved']
            from eval_harness.adapters.skill import build_ncr as exported_ncr
            with patch.dict('os.environ', {'ACF_EXPORT_SOURCE': str(root)}):
                assert exported_ncr(export).domains()
            with patch.dict('os.environ', {'ACF_EXPORT_SOURCE': ''}):
                try:
                    exported_ncr(export)
                    raise AssertionError('export accepted without live source verification')
                except ValueError:
                    pass
            (export/'SKILL.md').write_text('tampered exported guidance')
            try:
                verify_export(root, export)
                raise AssertionError('tampered export accepted')
            except ValueError:
                pass
            events = append_event(events,'block',targets=['metric:sales.orders'],reason='new source drift',
                                  source_evidence={'source':'dbt','revision':'source-3'},revision=rev)
            try:
                build_ncr(root, branch_test=False)
                raise AssertionError('stale context injected into governed answer')
            except ValueError:
                pass
    print('test_merge_approval: OK')


if __name__=='__main__':
    run()
