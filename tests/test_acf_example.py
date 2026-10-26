"""Complete synthetic 0.3 graph and cohort/renewal contract exercise; no live data."""
from copy import deepcopy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from acf_runtime.loader import load_context
from acf_runtime.matching import match_registry
from acf_runtime.impact import lineage_impact
from eval_harness.matching import normalize,relation
from eval_harness.grader import compare_snapshot,grade_answer

EXAMPLE=ROOT/'examples/example-acf-03-company'


def run():
    columns={
      'customers':['customer_id','is_test','first_order_date','segment','signup_year'],
      'orders':['order_id','customer_id','is_test','order_date'],
      'revenue_entries':['amount','measure_name','activity_date','channel','revenue_stream'],
      'subscription_terms':['term_id','renewed_from_term_id','is_test','outcome_decided','term_end_date','plan','segment']}
    manifest={'nodes':{f'model.demo.{name}':{'name':name,'unique_id':f'model.demo.{name}','resource_type':'model',
                   'columns':{col:{} for col in cols}} for name,cols in columns.items()}}
    registry=load_context(EXAMPLE,schemas=ROOT/'schemas',manifests={'demo':manifest})
    assert not registry.errors, [str(e) for e in registry.errors]
    assert not registry.diagnostics, [str(e) for e in registry.diagnostics]
    assert len(registry.metrics)==10 and len(registry.methods)==2 and len(registry.seeds)==9
    for node in registry.metrics+registry.methods+registry.seeds:
        assert 'status' not in node.data
        for review in node.data.get('review_history', []):
            if review.get('status') == 'confirmed':
                assert review['approver'] == 'fictional-example-reviewer'
    family=registry.lookup('revenue','revenue')
    assert len(family)==5
    assert match_registry(registry,{'metric':'revenue'},'revenue')['relation']=='ambiguous'
    assert registry.nodes['method:refund-impact'].effective_status=='draft'
    assert any('refund_attribution' in reason for reason in registry.nodes['method:refund-impact'].blocking_reasons)
    assert registry.nodes['metric:revenue.recognized_revenue'].effective_status=='confirmed'
    renewal=registry.nodes['metric:subscriptions.renewal_rate']
    assert renewal.data['expression']['ratio']['zero_denominator'] is None
    assert renewal.lineage=={('demo','subscription_terms')}
    for name in ('renewed_terms','churned_terms'):
        node=registry.nodes['metric:subscriptions.'+name]
        assert node.defined and not node.data.get('expression')
        assert node.dependencies=={'pattern:domains/subscriptions/reference.md#pattern-renewal-outcomes'}
        assert node.dimensions=={'plan','segment'}
    impact=lineage_impact(registry,{('demo','subscription_terms')})
    assert 'seed:renewal-by-plan.seed.yaml' in {n['id'] for n in impact['objects']}
    a=registry.nodes['seed:cohort-activity.seed.yaml'].data['ir']
    b=deepcopy(a);b['parameters']['cohort_anchor']='activity'
    defs=registry.definitions()
    assert relation(normalize(a,'customers',defs),normalize(b,'customers',defs))=='equivalent'
    c=registry.nodes['seed:cohort-acquisition.seed.yaml'].data['ir']
    assert relation(normalize(a,'customers',defs),normalize(c,'customers',defs))=='same_metric_new_slice'
    assert match_registry(registry,b,'customers')['relation']=='equivalent'
    assert not registry.nodes['seed:cohort-notebook-pending.seed.yaml'].data.get('approver')
    assert registry.nodes['seed:cohort-notebook-pending.seed.yaml'].approval_state=='proposed'
    negatives=[n for n in registry.seeds if n.data['expected']['kind']=='negative']
    assert {n.data['expected']['reason'] for n in negatives}=={'lack_data','unresolved_semantics'}
    # Finite fictional observations exercise the method's decisions independently
    # of a database. No figures are written into qualitative context documents.
    customers={'A':('returning',False),'B':('returning',False),'LATE':('returning',False),
               'EMPTY':('empty',False),'TEST':('returning',True)}
    orders=[('A','2025-12-20',False),('A','2026-01-03',False),('A','2026-01-04',False),('B','2026-01-05',False),
            ('A','2026-02-10',False),('A','2026-02-11',False),('B','2026-02-20',False),
            ('B','2026-02-12',True),('LATE','2026-02-05',False),('TEST','2026-01-10',False),('TEST','2026-02-10',False)]
    snapshot=registry.nodes['seed:cohort-partial-snapshot.seed.yaml'].data
    params=snapshot['ir']['parameters'];base=params['base_window'];follow=params['followup_window'];asof=params['as_of_date']
    eligible=[(customer,when) for customer,when,test in orders if not test and not customers[customer][1] and when<asof]
    cohort={customer for customer,when in eligible if base['start']<=when<base['end']}
    returning={customer for customer,when in eligible if follow['start']<=when<follow['end']} & cohort
    rows=[]
    for segment in sorted({segment for segment,test in customers.values() if not test}):
        members={customer for customer in cohort if customers[customer][0]==segment}
        returned=len(members & returning)
        rows.append({'cohort_label':'January activity','cohort_key':segment,'cohort_size':len(members),
            'returned':returned,'retention_rate':returned/len(members) if members else None,
            'followup_complete':follow['end']<=asof})
    assert cohort=={'A','B'} and returning=={'A'}
    first_order={customer:min(when for who,when in eligible if who==customer) for customer,_ in eligible}
    acquisitions={customer for customer,when in first_order.items() if base['start']<=when<base['end']}
    assert acquisitions=={'B'} and not (acquisitions & returning)
    assert compare_snapshot(rows,snapshot['expected']).status=='pass'
    wrong=deepcopy(rows);next(row for row in wrong if row['cohort_size']==0)['retention_rate']=0
    assert compare_snapshot(wrong,snapshot['expected']).status=='fail'
    assert compare_snapshot(rows+[rows[0]],snapshot['expected']).status=='fail'
    method=registry.nodes['method:cohort-retention'].data
    answer={'outcome':'answer','sql':'synthetic implementation proposal','explanation':'Activity anchor; explicit windows; partial follow-up.',
            'disclosures':['activity','2026-01-01 to 2026-02-01; 2026-02-01 to 2026-03-01','Partial follow-up']}
    execution={'status':'ok','rows':rows,'as_of':asof,
               'comparison_evidence':{'anchor_cohort_sizes':{'returning':len(cohort),'empty':0}}}
    obligations=[]
    def synthetic_judge(evidence,expected):
        obligations.append(expected['kind'])
        return {'passed':True,'reason':'Synthetic semantic-review stub, not live AI evidence'}
    verdict=grade_answer(snapshot['expected'],answer,synthetic_judge,method=method,execution=execution)
    assert verdict.status=='pass' and 'method_disclosures' in obligations and 'method_relationship' in obligations
    def missing_disclosure(evidence,expected):
        return {'passed':expected['kind']!='method_disclosures','reason':'Synthetic missing-disclosure failure'}
    assert grade_answer(snapshot['expected'],answer,missing_disclosure,method=method,execution=execution).status=='fail'
    assert grade_answer(snapshot['expected'],answer,synthetic_judge,method=method).status=='skipped'
    print('test_acf_example: OK')


if __name__=='__main__':run()
