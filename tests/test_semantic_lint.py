"""Optional semantic comparisons, bounded inputs, cache integrity and safe PR data."""
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from acf_fixtures import context,metric,method,write,METHOD_BODY
from acf_runtime import semantic_lint as lint
from acf_runtime.impact import snapshot


def fixture(root):
    context(root)
    write(root,'domains/sales/metrics/orders.yaml',metric())
    write(root,'methods/repeat.md',method(),METHOD_BODY)
    (root/'domains/sales/reference.md').write_text('# Orders reference\nUse all orders including test orders.\n')
    (root/'domains/sales/context.md').write_text('# Orders context\nExclude test orders from every analysis.\n')
    for relative in ('evals/verified/secret.sql','evals/observed/queue.jsonl','evals/runs/rows.json','notebooks/secret.ipynb'):
        path=root/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('PRIVATE_DO_NOT_SEND')


def warning(task,model):
    assert 'PRIVATE_DO_NOT_SEND' not in json.dumps(task)
    return {'warnings':[{'code':task['kind'],'message':'Possible scope mismatch; ask the analyst.',
        'evidence':[{'document':d['id'],'quote':d['content'].strip().splitlines()[0]} for d in task['documents']]}]}


def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout.decode().strip()


def run():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); fixture(root)
        before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
        with patch.object(lint,'tasks',side_effect=AssertionError('must skip before reading')), patch.dict(os.environ,{},clear=True):
            assert lint.lint(root)['category']=='key_unavailable'
        calls=[]
        def ask(task,model): calls.append(task); return warning(task,model)
        report=lint.lint(root,enabled=True,request=ask)
        assert report['status']=='reviewed' and len(calls)==3 and len(report['warnings'])==3
        assert {t['kind'] for t in calls}==set(lint.CODES)
        assert all(p.read_bytes()==raw for p,raw in before.items())
        for path in (root/'.nodal/semantic-lint').glob('*.json'):
            data=json.loads(path.read_text())
            assert set(data)=={'key','version','model','warnings'}
            assert 'PRIVATE_DO_NOT_SEND' not in path.read_text()
            assert path.stat().st_mode & 0o777==0o600
        report=lint.lint(root,enabled=True,request=ask)
        assert len(calls)==3 and all(c['cached'] for c in report['comparisons'])
        lint.lint(root,enabled=True,request=ask,model='different-test-model')
        assert len(calls)==6
        with patch.object(lint,'VERSION','synthetic-prompt-version'):
            lint.lint(root,enabled=True,request=ask)
        assert len(calls)==9
        (root/'domains/sales/context.md').write_text('# Changed context\nStill exclude test orders.\n')
        lint.lint(root,enabled=True,request=ask)
        assert len(calls)==10  # only the changed comparison invalidates
        for path in (root/'.nodal/semantic-lint').glob('*.json'): path.write_text('{not JSON')
        lint.lint(root,enabled=True,request=ask)
        assert len(calls)==13
        safe=lint.markdown({'status':'reviewed','category':'warning_only','comparisons':[],
            'warnings':[{'code':'routing_conflict','message':'@all <script> [click](https://bad.invalid)',
                         'evidence':[{'document':'methods/repeat.md','quote':'@owner text'}]}]})
        assert '@all' not in safe and '<script>' not in safe and '[click](' not in safe
    for bad in (None, {'warnings':'bad'}, {'warnings':[{'code':'wrong','message':'x','evidence':[]}]},
                {'warnings':[{'code':'routing_conflict','message':'invented', 'evidence':[
                    {'document':'/outside/secret','quote':'secret'}, {'document':'bad','quote':'bad'}]}]}):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); fixture(root)
            report=lint.lint(root,enabled=True,request=lambda *args:bad)
            assert report['status']=='partial' and not report['warnings']
            assert not (root/'.nodal/semantic-lint').exists()
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); fixture(root)
        with patch.object(lint,'_ask',side_effect=RuntimeError('PRIVATE_ERROR')):
            report=lint.lint(root,enabled=True)
        assert 'PRIVATE_ERROR' not in json.dumps(report) and report['status']=='partial'
        (root/'domains/sales/reference.md').write_text('x'*(lint.MAX_INPUT_BYTES+1))
        calls=[]
        def ask(task,model): calls.append(task); return {'warnings':[]}
        report=lint.lint(root,enabled=True,request=ask)
        assert len(calls)==1 and calls[0]['kind']=='method_decision_conflict'
        assert sum(c['category']=='input_limit' for c in report['comparisons'])==2
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); fixture(root)
        with patch.object(lint,'MAX_REQUESTS',1):
            report=lint.lint(root,enabled=True,request=lambda *args:{'warnings':[]})
        assert sum(c['category']=='request_limit' for c in report['comparisons'])==2
        # A poisoned cache never grants arbitrary paths or fabricated quotations.
        path=next((root/'.nodal/semantic-lint').glob('*.json'))
        stored=json.loads(path.read_text()); stored['warnings']=[{'code':'routing_conflict','message':'invented',
            'evidence':[{'document':'domains/sales/reference.md','quote':'absent quote'},
                        {'document':'domains/sales/metrics/orders.yaml#normalized','quote':'absent quote'}]}]
        path.write_text(json.dumps(stored))
        report=lint.lint(root,enabled=True,request=lambda *args:{'warnings':[]})
        assert not report['warnings']
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); fixture(root)
        # Reject internal and external symlink context inputs, not just '..'.
        external=root.parent/(root.name+'-private.txt'); external.write_text('PRIVATE_DO_NOT_SEND')
        path=root/'domains/sales/reference.md'; path.unlink(); path.symlink_to(external)
        try:
            report=lint.lint(root,enabled=True,request=warning)
            assert report['category']=='context_unavailable_or_invalid'
        finally: external.unlink()
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); fixture(root)
        git(root,'init','--quiet'); git(root,'add','.')
        git(root,'-c','user.name=Fictional Test','-c','user.email=test@example.invalid','-c','commit.gpgsign=false','commit','-qm','fictional data')
        malicious=root/'acf_runtime/semantic_lint.py'; malicious.parent.mkdir()
        malicious.write_text("raise RuntimeError('UNTRUSTED_CODE_EXECUTED')")
        git(root,'add','.'); git(root,'-c','user.name=Fictional Test','-c','user.email=test@example.invalid','-c','commit.gpgsign=false','commit','-qm','untrusted code fixture')
        revision=git(root,'rev-parse','HEAD')
        spec=importlib.util.spec_from_file_location('semantic_cli',ROOT/'.ci/semantic_lint.py')
        cli=importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        output=io.StringIO()
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'synthetic-only'}), patch.object(lint,'_ask',side_effect=warning), redirect_stdout(output):
            assert cli.main(['--repo-root',str(root),'--revision',revision,'--format','json'])==0
        assert len(json.loads(output.getvalue())['warnings'])==3
        assert 'UNTRUSTED_CODE_EXECUTED' not in output.getvalue()
        original=(root/'context.config.yaml').read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            assert cli.main(['--repo-root',str(root),'--out','context.config.yaml'])==0
            assert cli.main(['--repo-root',str(root),'--revision','missing'])==0
        assert (root/'context.config.yaml').read_bytes()==original
    print('test_semantic_lint: OK')


if __name__=='__main__': run()
