"""Regression cases from the 2026-10-27 adversarial review; no live services."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_fixtures import context, domain, metric, method, seed, write, METHOD_BODY
from acf_runtime import load_context
from acf_runtime.governance import append_event, validate_ledger, object_digests, digest, context_files, authority_request
from acf_runtime.impact import lineage_impact
from eval_harness.grader import compare_snapshot
from scripts.compile_skill import compile_skill, verify_export


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE).decode().strip()


def save(root):
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
    return git(root, 'rev-parse', 'HEAD')


def approval(root, revision, **extra):
    registry = load_context(root, branch_test=True)
    return dict(revision=revision, content_digest=digest(context_files(root)), branch='main',
                checks=['checked'], review=['human'], protection='protected', object_digests=object_digests(registry), **extra)


def authority(events):
    def respond(request):
        now = datetime.now(timezone.utc)
        return dict(version=1, nonce=request['nonce'], approval_branch='main', checked_at=now.isoformat(),
                    expires_at=(now+timedelta(minutes=5)).isoformat(), events=events,
                    freshness=dict(revision=request['revision'], content_digest=request['content_digest'],
                        checked_at=now.isoformat(), expires_at=(now+timedelta(hours=1)).isoformat(),
                        sources={s:dict(status='checked', revision='source', digest='hash') for s in request['sources']}))
    return respond


def run():
    # Numeric keys follow value comparison semantics, without conflating bool/string.
    expected={'kind':'value_at_snapshot','value':[{'year':2024,'n':1}], 'key_columns':['year']}
    assert compare_snapshot([{'year':2024.0,'n':1}],expected).status=='pass'
    for value in ('2024', True):
        assert compare_snapshot([{'year':value,'n':1}],expected).status=='fail'
    assert compare_snapshot([{'year':2024,'n':1},{'year':2024.0,'n':1}],expected).status=='fail'
    drift=module('review_drift', '.ci/drift.py')
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'context';context(root)
        write(root,'domains/sales/metrics/orders.yaml',metric())
        m=method();m['decisions'][0]['id']='step-1'
        write(root,'methods/repeat.md',m,METHOD_BODY.replace('`identity`','`step-1`'))
        assert not load_context(root,branch_test=True).errors
        write(root,'methods/repeat.md',m,METHOD_BODY.replace('`identity`','`step-1`')+'\n2. Divide by / 7 (`step-1`).\n')
        assert any(d.code=='constant.undeclared' for d in load_context(root,branch_test=True).diagnostics)
        (root/'methods/repeat.md').unlink()
        # Config-only domain lineage blocks every owned object, not just a report row.
        from acf_runtime.loader import read_yaml
        cfg=read_yaml(root/'context.config.yaml');cfg['domains']={'sales':{'lineage':[{'source':'config_only','models':['external']}]}}
        cfg['lineage_sources'].append({'id':'config_only','type':'dbt'})
        write(root,'context.config.yaml',cfg)
        registry=load_context(root,branch_test=True)
        assert 'config_only' in authority_request(registry)['sources']
        impact=lineage_impact(registry,{('config_only','external')})
        assert 'metric:sales.orders' in impact['roots']
        manifest={'nodes':{},'sources':{}}
        for kind in ('model','seed','snapshot','source'):
            key=f'{kind}.p.{kind}_table'
            manifest['sources' if kind=='source' else 'nodes'][key]={
                'name':kind+'_table','resource_type':kind,'columns':{'id':{'name':'id'}}}
        manifest_path=Path(td)/'manifest.json';manifest_path.write_text(json.dumps(manifest))
        names={f'{k}.p.{k}_table' for k in ('model','seed','snapshot','source')}|{'model_table'}
        current,missing,unchecked=drift.compute_current({'dbt':names},{'dbt':str(manifest_path)})
        assert set(current['dbt'])==names and not missing and not unchecked
        # Protected merges inherit reviewed clearance only with ancestry AND an
        # unchanged affected definition/dependency/prose scope.
        git(root,'init','-q');rev=save(root)
        events=append_event([], 'approve', **approval(root,rev))
        events=append_event(events,'block',targets=['metric:sales.orders'],reason='source changed',source_evidence={'revision':'src2'})
        block=events[-1]['id']
        events=append_event(events,'clear',block=block,revision=rev,checks=['fresh pass'],reason='reviewed repair',source_evidence={'revision':'src2'})
        domain(root,'finance');write(root,'domains/finance/metrics/revenue.yaml',metric('revenue'))
        next_rev=save(root)
        events=append_event(events,'approve',**approval(root,next_rev,ancestors=[rev]))
        assert next_rev in validate_ledger(events)[1][block]['cleared_revisions']
        changed=metric();changed['definition']='Changed interpretation'
        write(root,'domains/sales/metrics/orders.yaml',changed)
        changed_rev=save(root)
        events=append_event(events,'approve',**approval(root,changed_rev,ancestors=[rev,next_rev]))
        assert changed_rev not in validate_ledger(events)[1][block]['cleared_revisions']
        # An unrelated new block is never cleared by that inherited clearance.
        events=append_event(events,'block',targets=['metric:finance.revenue'],reason='new source change',source_evidence={'revision':'src3'})
        assert not validate_ledger(events)[1][events[-1]['id']]['cleared_revisions']
    with tempfile.TemporaryDirectory() as td:
        base=Path(td);root=base/'checkout-one';context(root)
        write(root,'domains/sales/metrics/orders.yaml',metric())
        domain(root,'pending');write(root,'domains/pending/metrics/pending.yaml',metric('pending',status='draft'))
        write(root,'domains/sales/metrics/unfinished.yaml',metric('unfinished',status='draft'))
        write(root,'entities/pending.yaml',{'entities':[{'name':'unfinished-entity','description':'pending meaning','status':'draft'}]})
        (root/'domains/sales/reference.md').write_text('UNSAFE_PROSE about unfinished definitions')
        git(root,'init','-q');rev=save(root)
        events=append_event([],'approve',**approval(root,rev))
        with patch.dict(os.environ,{'ACF_BRANCH_TEST':'0'}),patch('acf_runtime.governance.read_authority',side_effect=authority(events)):
            from eval_harness.adapters.acf import build_ncr
            ncr=build_ncr(root)
            assert ncr.domains()==['sales']
            assert 'UNSAFE_PROSE' not in ncr.context_for('sales')
            assert 'unfinished' not in ncr.context_for('sales')
            out,stats=compile_skill(root,base/'dist',None,False)
            assert stats['domains']==['sales']
            relocated=base/'different-checkout-name';shutil.copytree(root,relocated)
            # Clock and folder name do not enter hashed artifact bytes.
            with patch('scripts.compile_skill.datetime.date') as date:
                date.today.return_value=datetime(2099,1,1).date()
                assert verify_export(relocated,out)['approved']
        # Rebuild from scratch removes generated stale domain references.
        with patch.dict(os.environ,{'ACF_BRANCH_TEST':'1'}):
            out,_=compile_skill(root,base/'draft-export',None,True)
            assert (out/'references/pending.md').exists()
            shutil.rmtree(root/'domains/pending')
            out,_=compile_skill(root,base/'draft-export',None,True)
            assert not (out/'references/pending.md').exists()
            (out/'personal.txt').write_text('user content')
            try:compile_skill(root,base/'draft-export',None,True)
            except ValueError:pass
            else:raise AssertionError('user-added file was overwritten')
            assert (out/'personal.txt').read_text()=='user content'
    merge_history()
    real_ci_regression()
    import yaml
    workflow=yaml.safe_load((ROOT/'template/.github/workflows/context-drift.yml').read_text())
    triggers=workflow.get('on', workflow.get(True))
    assert 'push' in triggers and 'acf-governance' in triggers['push']['branches-ignore']
    assert '${{ github.ref }}' in workflow['concurrency']['group']
    print('test_adversarial_review: OK')


def merge_history():
    from acf_runtime.regrade import approved_history
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);context(root)
        write(root,'domains/sales/metrics/orders.yaml',metric())
        git(root,'init','-q');save(root);git(root,'branch','-M','main')
        git(root,'checkout','-qb','proposal')
        proposed=seed()
        for field in ('status','approver','confirmed_at'):proposed.pop(field,None)
        write(root,'evals/seeds/orders.seed.yaml',proposed);save(root)
        git(root,'checkout','-q','main')
        git(root,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            'merge','--no-ff','proposal','-m','Reviewed merge')
        merged=git(root,'rev-parse','HEAD')
        events=append_event([],'approve',**approval(root,merged))
        (root/'unrelated.txt').write_text('unrelated');save(root)
        with patch('acf_runtime.governance.read_authority',side_effect=authority(events)):
            seeds=load_context(root,branch_test=True).seeds
            records=approved_history(root,seeds)
            assert records[seeds[0].id]['revision']==merged
            assert records[seeds[0].id]['approval_event']==events[0]['id']


def real_ci_regression():
    from test_regression import EXECUTOR
    ci=module('review_regression_ci','.ci/regression_ci.py')
    with tempfile.TemporaryDirectory() as td:
        base=Path(td);root=base/'source';context(root)
        from acf_runtime.loader import read_yaml
        cfg=read_yaml(root/'context.config.yaml');cfg['warehouse']='sqlite';cfg['verified_sql']={'encryption':'age','recipients':['age1fixture']}
        write(root,'context.config.yaml',cfg)
        write(root,'domains/sales/metrics/orders.yaml',metric())
        write(root,'evals/seeds/orders.seed.yaml',seed(expected={'kind':'value_at_snapshot','value':2,'as_of':'2026-10-01'},
            verified_query_file='evals/verified/orders.sql',provenance='dashboard'))
        for name in ('acf_runtime','eval_harness','schemas'):
            shutil.copytree(ROOT/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
        (root/'scripts').mkdir();shutil.copy2(ROOT/'scripts/regress.py',root/'scripts/regress.py')
        (root/'evals/verified').mkdir(parents=True)
        # Test-only codec and executor. The real CI wrapper, loader, governance,
        # regression CLI and query/receipt validation all run without stubbing.
        (root/'evals/verified/orders.sql.age').write_text('fixture:SELECT COUNT(*) AS orders FROM orders WHERE test = 0')
        git(root,'init','-q');rev=save(root)
        events=append_event([],'approve',**approval(root,rev))
        state=base/'authority.json';state.write_text(json.dumps(events))
        provider=base/'authority.py'
        provider.write_text('''import json,sys
from datetime import datetime,timedelta,timezone
r=json.load(sys.stdin);now=datetime.now(timezone.utc)
events=json.load(open(sys.argv[1]))
print(json.dumps(dict(version=1,nonce=r['nonce'],approval_branch='main',checked_at=now.isoformat(),expires_at=(now+timedelta(minutes=5)).isoformat(),events=events,freshness=dict(revision=r['revision'],content_digest=r['content_digest'],checked_at=now.isoformat(),expires_at=(now+timedelta(hours=1)).isoformat(),sources={s:dict(status='checked',revision='source',digest='hash') for s in r['sources']}))))
''')
        bins=base/'bin';bins.mkdir();age=bins/'age'
        age.write_text('#!'+sys.executable+'\nimport sys\npayload=sys.stdin.buffer.read();assert payload.startswith(b"fixture:");sys.stdout.buffer.write(payload[8:])\n');age.chmod(0o700)
        executor=base/'executor.py';executor.write_text(EXECUTOR)
        room=ci.prepare(root,base)
        assert git(room/'context','rev-parse','HEAD')==rev
        env={**os.environ,'ACF_BRANCH_TEST':'0','ACF_GOVERNANCE_COMMAND':json.dumps([sys.executable,str(provider),str(state)]),
             'PATH':str(bins)+os.pathsep+os.environ['PATH'],'NODAL_REGRESSION_EXECUTOR':json.dumps([sys.executable,str(executor),'ok']),
             'NODAL_VERIFIED_IDENTITY':'fixture-identity'}
        code,report=ci.execute(room,base,env)
        assert code==0 and report['results'][0]['status']=='pass', (code,report)
        ci.cleanup(room,base)


if __name__=='__main__':run()
