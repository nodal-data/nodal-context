"""Fresh independent checks, historical approval, dependency gates and seed writes."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_fixtures import context, metric, method, seed, write, METHOD_BODY, APPROVAL
from acf_runtime import regrade
from acf_runtime.loader import load_context, read_yaml
from acf_runtime.markdown import render_reference, draft_pattern, pattern_span
from eval_harness.adapters.acf import build_ncr


class Provider:
    def __init__(self, *, available=True, verdict=True, mutate=None):
        self.enabled, self.verdict, self.mutate = available, verdict, mutate
        self.questions, self.contexts, self.obligations = [], [], []
    def available(self):
        return self.enabled
    def generate(self, question, context_text=None, model=None):
        self.questions.append(question); self.contexts.append(context_text)
        assert 'SECRET_EXPECTATION' not in context_text and 'seed:' not in context_text
        return {'outcome': 'answer', 'sql': 'SELECT COUNT(*) FROM orders WHERE NOT test',
                'python': '', 'assumptions': [], 'reason': '',
                'explanation': 'Canonical customer', 'disclosures': ['window used']}
    def judge(self, evidence, obligations, model=None):
        self.obligations.append(obligations)
        if self.mutate:
            self.mutate(); self.mutate = None
        return {'passed': self.verdict, 'reason': 'synthetic verdict'}


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True).stdout.decode().strip()


def save(root):
    git(root, 'add', 'context.config.yaml', 'domains', 'evals', 'entities', 'methods')
    git(root, '-c', 'user.name=Fictional Test', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fictional fixture')
    return git(root, 'rev-parse', 'HEAD')


def setup(root):
    context(root)
    write(root, 'domains/sales/metrics/orders.yaml', metric())
    write(root, 'methods/repeat.md', method(), METHOD_BODY)
    write(root, 'entities/customer.yaml', {'entities': [{'name':'customer', 'description':'Canonical customer',
        'status':'confirmed', 'lineage':[{'source':'dbt', 'models':['orders']}]}]})
    write(root, 'evals/seeds/orders.seed.yaml', seed(expected={'kind':'sql_shape', 'must_include':['SECRET_EXPECTATION']},
        variants=[{'text':'Eligible orders last month by channel?', 'provenance':'observed', 'observed_at':'2026-10-20'}]))
    value = seed(expected={'kind':'semantic_entity', 'entity':'customer'}); value.pop('ir')
    write(root, 'evals/seeds/customer.seed.yaml', value)
    write(root, 'evals/seeds/snapshot.seed.yaml', seed(expected={'kind':'value_at_snapshot','value':42,'as_of':'2026-10-20'}))
    write(root, 'evals/seeds/negative.seed.yaml', seed(expected={'kind':'negative','reason':'lack_data'}))
    write(root, 'evals/seeds/method.seed.yaml', seed(ir={'method':'repeat','metrics':['orders'],'parameters':{'window':'last_month'}}))
    git(root, 'init', '--quiet'); save(root)
    for path in (root/'evals/seeds').glob('*.yaml'):
        path.write_text(path.read_text().replace('status: confirmed', 'status: draft'))
    assert not load_context(root).errors


def result(report, name='orders'):
    return next(r for r in report['results'] if r['seed'] == 'seed:'+name+'.seed.yaml')


def reject(call):
    try: call()
    except ValueError: return
    raise AssertionError('expected rejection')


def run():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        provider = Provider()
        before = {p:p.read_bytes() for p in root.rglob('*') if p.is_file() and '.git' not in p.parts}
        report = regrade.run_regrade(root, provider=provider)
        assert result(report)['eligible']
        assert result(report, 'customer')['eligible']
        assert result(report, 'snapshot')['category'] == 'human_review_required'
        assert result(report, 'negative')['category'] == 'human_review_required'
        assert result(report, 'method')['category'] == 'fresh_checks_incomplete'  # no invented execution
        assert len(provider.questions) == 4  # original + variant + entity + method
        assert any(o.get('entity_definitions') for o in provider.obligations)
        assert all(p.read_bytes() == raw for p,raw in before.items())
        reject(lambda: regrade.run_regrade(root, provider=Provider(), restore=True))
        report = regrade.run_regrade(root, provider=Provider())
        for name in ('orders', 'customer'):
            assert result(report, name)['category'] == 'eligible_for_restoration'
            doc = read_yaml(root / ('evals/seeds/'+name+'.seed.yaml'))
            assert doc['status'] == 'draft'
            assert doc['approver'] == APPROVAL['approver'] and doc['confirmed_at'] == APPROVAL['confirmed_at']
        assert 'SECRET_EXPECTATION' not in json.dumps(report)
        assert (root/report['evidence']).stat().st_mode & 0o777 == 0o600
        assert read_yaml(root/'evals/seeds/method.seed.yaml')['status'] == 'draft'
        assert (root/'methods/repeat.md').read_bytes() == before[root/'methods/repeat.md']
        assert regrade.run_regrade(root, provider=Provider(), seed_ids=['seed:orders.seed.yaml'])['results'][0]['category'] == 'eligible_for_restoration'
    for verdict, available, category in [(False,True,'fresh_grade_failed'), (True,False,'judge_unavailable'),
                                         ('true',True,'fresh_checks_incomplete')]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); setup(root)
            report = regrade.run_regrade(root, provider=Provider(verdict=verdict,available=available))
            assert result(report)['category'] == category, report
            assert read_yaml(root/'evals/seeds/orders.seed.yaml')['status'] == 'draft'
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        # A pass while the metric is draft cannot restore its seed. Reconfirming
        # that metric alone doesn't change seed status or reuse the earlier pass.
        write(root, 'domains/sales/metrics/orders.yaml', metric(status='draft'))
        report = regrade.run_regrade(root, provider=Provider())
        assert result(report)['status'] == 'pass' and result(report)['category'] == 'dependency_review_pending'
        write(root, 'domains/sales/metrics/orders.yaml', metric())
        report = regrade.run_regrade(root, provider=Provider(available=False))
        assert result(report)['category'] == 'judge_unavailable'
        assert read_yaml(root/'evals/seeds/orders.seed.yaml')['status'] == 'draft'
        report = regrade.run_regrade(root, provider=Provider())
        assert result(report)['category'] == 'eligible_for_restoration'
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        changed = read_yaml(root/'evals/seeds/orders.seed.yaml')
        changed['expected']['must_include'] = ['Changed business definition']
        write(root,'evals/seeds/orders.seed.yaml', changed)
        assert result(regrade.run_regrade(root, provider=Provider()))['category'] == 'authored_interpretation_changed'
        changed = metric(); changed['expression']['allowed_dimensions'] = ['date']
        # Remove the unrelated method to keep its declared output dimensions valid.
        m = method(); m['output']['dimensions'] = []
        write(root,'methods/repeat.md',m,METHOD_BODY)
        write(root,'domains/sales/metrics/orders.yaml',changed)
        original = seed(status='draft',expected={'kind':'sql_shape','must_include':['SECRET_EXPECTATION']},
            variants=[{'text':'Eligible orders last month by channel?', 'provenance':'observed','observed_at':'2026-10-20'}])
        write(root,'evals/seeds/orders.seed.yaml',original)
        report = regrade.run_regrade(root, provider=Provider())
        assert result(report)['category'] == 'definition_or_dimension_review_required'
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        path = root/'domains/sales/metrics/orders.yaml'
        provider = Provider(mutate=lambda: path.write_text(path.read_text()+'\n# concurrent human note\n'))
        reject(lambda: regrade.run_regrade(root, provider=provider))
        assert read_yaml(root/'evals/seeds/orders.seed.yaml')['status'] == 'draft'
        # Uncommitted new seeds cannot fabricate historical approval.
        write(root,'evals/seeds/new.seed.yaml',seed(status='draft'))
        assert result(regrade.run_regrade(root,provider=Provider()),'new')['category'] == 'previous_human_approval_unavailable'
        # A malformed answer cannot be blessed by an overly permissive judge.
        provider = Provider()
        with patch.object(provider, 'generate', return_value={'outcome':'answer','sql':42}):
            report = regrade.run_regrade(root,provider=provider)
        assert result(report)['category'] == 'fresh_checks_incomplete'
        assert not provider.obligations
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); setup(root)
        original=read_yaml(root/'evals/seeds/orders.seed.yaml')
        newer=deepcopy(original); newer.update(status='confirmed',intent='A different reviewed meaning')
        write(root,'evals/seeds/orders.seed.yaml',newer); save(root)
        write(root,'evals/seeds/orders.seed.yaml',original)
        report=regrade.run_regrade(root,provider=Provider())
        assert result(report)['category']=='authored_interpretation_changed'
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); setup(root)
        provider=Provider()
        def fail_variant(evidence,obligations,model=None):
            return {'passed':len(provider.questions)!=2,'reason':'synthetic variant mismatch'}
        provider.judge=fail_variant
        # Select one seed so the second independent answer is its variant.
        report=regrade.run_regrade(root,provider=provider,seed_ids=['seed:orders.seed.yaml'])
        assert result(report)['category']=='fresh_grade_failed'
        assert read_yaml(root/'evals/seeds/orders.seed.yaml')['status']=='draft'
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); setup(root)
        before={p:p.read_bytes() for p in root.rglob('*.yaml')}
        reject(lambda:regrade.run_regrade(root,provider=Provider(),restore=True))
        assert all(p.read_bytes()==raw for p,raw in before.items())
    # Fenced SQL/Python headings/anchors/status words never terminate or change a
    # real pattern's status. Both compiled and injected contexts omit drafts.
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); setup(root)
        text='# Reference\n\n<a id="pattern-old"></a>\n### Old\nWithout this: wrong join\n```python\n# Fake heading\nstatus: confirmed\n```\n\n<a id="pattern-good"></a>\n### Good\nWithout this: correct join\nKEEP_GOOD\n'
        text=draft_pattern(text,'pattern-old')
        a,b=pattern_span(text,'pattern-old'); assert 'status: confirmed' in text[a:b] and 'KEEP_GOOD' not in text[a:b]
        rendered,count=render_reference(text); assert count==1 and 'Fake heading' not in rendered and 'KEEP_GOOD' in rendered
        (root/'domains/sales/reference.md').write_text(text)
        assert 'Fake heading' not in build_ncr(root).context_for('sales')
        sys.path.insert(0,str(ROOT/'scripts'))
        from compile_skill import compile_skill
        output,stats=compile_skill(root,root/'dist',None,include_drafts=False)
        assert 'Fake heading' not in (output/'references/sales.md').read_text()
        output,stats=compile_skill(root,root/'draft-dist',None,include_drafts=True)
        assert 'DRAFT — unconfirmed query pattern' in (output/'references/sales.md').read_text()
    print('test_regrade: OK')


if __name__=='__main__': run()
