"""ACF 0.3 restricted grammar, recursive filters and transitive column checks."""
from copy import deepcopy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime import load_context
from acf_runtime.expressions import MeasureParser
from acf_runtime.loader import Schemas
from acf_fixtures import context, metric, write


def run():
    for measure in ['SUM(amount) / COUNT(DISTINCT customer_id)', 'COUNT(*)',
                    '-(AVG(amount) + 1.5e2) * metric(base)', 'MIN(t.amount) - MAX(t.amount)',
                    'metric(with-hyphens) / 100', 'COUNT(distinct customer_id)']:
        MeasureParser(measure).parse()
    for measure in ['amount', 'SUM(amount) FROM fact', 'COUNT(*) OVER ()',
                    'SUM(CASE WHEN x THEN 1 END)', 'SUM(x + y)', 'SUM(SUM(x))',
                    'metric(base); DROP TABLE t', 'metric(base) extra', '1 2',
                    'COUNT(DISTINCT *)', 'SUM(*)', 'COUNT(1)', 'ABS(SUM(x))',
                    'SUM(x) -- comment', '<as_of_date>', '', 'SUM(x) +', 'metric()']:
        try:
            MeasureParser(measure).parse()
        except ValueError:
            pass
        else:
            raise AssertionError(f'accepted invalid measure: {measure}')

    schema = Schemas(ROOT / 'schemas')
    group = {'any_of': [{'field': 'customer_id', 'op': 'is_null'},
                       {'all_of': [{'field': 'linked_date', 'op': '>', 'value': '<as_of_date>'}]}],
             'reason': 'Preserve unresolved-at-date aliases.'}
    base = metric('base', grain='alias', lineage=[{'source': 'dbt', 'models': ['identity']}],
                  expression={'measure': 'COUNT(*)', 'mandatory_filters': [group],
                              'allowed_dimensions': ['source_system']})
    ratio = metric('ratio', lineage='inherit', expression={
        'measure': 'metric(base) / metric(base)', 'allowed_dimensions': ['source_system'],
        'ratio': {'zero_denominator': None, 'reason': 'No population means no rate.'}})
    entity = deepcopy(base); entity['name'] = 'multi'
    entity['expression']['measure'] = 'COUNT(DISTINCT customer_id)'
    entity['expression']['entity_filters'] = [{'entity': 'customer_id', 'having': [
        {'measure': 'COUNT(DISTINCT source_system)', 'op': '>=', 'value': 2}]}]
    assert not schema.errors('metric', base)
    assert not schema.errors('ir', {'metric': 'base', 'filters': [group]})
    for bad in [{'any_of': []}, {'all_of': []}, {'any_of': [group], 'all_of': [group]},
                {'any_of': [group], 'field': 'x', 'op': '='},
                {'any_of': [{'field': 'x'}]}, {'field': 'x', 'op': '=', 'sql': 'x=1'}]:
        bad_doc = deepcopy(base); bad_doc['expression']['mandatory_filters'] = [bad]
        assert schema.errors('metric', bad_doc), bad
        assert schema.errors('ir', {'metric': 'base', 'filters': [bad]}), bad
    bad = deepcopy(ratio); del bad['grain']
    assert schema.errors('metric', bad)
    bad = deepcopy(entity); bad['expression']['entity_filters'][0]['having'] = []
    assert schema.errors('metric', bad)
    manifest = {'nodes': {'model.test.identity': {'resource_type': 'model', 'name': 'identity',
        'unique_id': 'model.test.identity', 'columns': {k: {} for k in
            ['customer_id', 'linked_date', 'source_system']}}}}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); context(root)
        def check(metrics, available=True):
            for path in root.glob('domains/sales/metrics/*.yaml'):
                path.unlink()
            for m in metrics:
                write(root, f"domains/sales/metrics/{m['name']}.yaml", m)
            return load_context(root, schemas=ROOT/'schemas', manifests={'dbt': manifest} if available else {})
        def codes(result):
            return {d.code for d in result.diagnostics}
        result = check([base, ratio, entity])
        assert not result.errors, [str(d) for d in result.errors]
        assert 'lineage.unchecked' in codes(check([base], available=False))
        for measure in ['COUNT(*)', 'SUM(customer_id)', '1']:
            bad = deepcopy(ratio); bad['expression']['measure'] = measure
            assert 'lineage.required' in codes(check([bad]))
        bad = deepcopy(ratio); bad['expression']['measure'] = 'metric(missing)'
        assert 'reference.missing' in codes(check([base, bad]))
        prose = deepcopy(base); del prose['expression']
        assert 'reference.undefined' in codes(check([prose, ratio]))
        bad['expression']['measure'] = 'metric(ratio)'
        assert 'graph.cycle' in codes(check([bad]))
        a, b = deepcopy(ratio), deepcopy(ratio)
        a['name'], b['name'] = 'a', 'b'
        a['expression']['measure'], b['expression']['measure'] = 'metric(b)', 'metric(a)'
        assert 'graph.cycle' in codes(check([a,b]))
        bad = deepcopy(ratio); bad['expression']['allowed_dimensions'] = ['linked_date']
        assert 'dimensions.reference' in codes(check([base, bad]))
        unspecified = deepcopy(base); del unspecified['expression']['allowed_dimensions']
        assert 'dimensions.reference' in codes(check([unspecified, ratio]))
        for location in ['entity', 'having', 'measure', 'filter']:
            bad = deepcopy(entity); expr = bad['expression']
            if location == 'entity': expr['entity_filters'][0]['entity'] = 'missing'
            elif location == 'having': expr['entity_filters'][0]['having'][0]['measure'] = 'COUNT(DISTINCT missing)'
            elif location == 'measure': expr['measure'] = 'SUM(identity.missing)'
            else: expr['mandatory_filters'][0]['any_of'][1]['all_of'][0]['field'] = 'missing'
            assert 'lineage.column' in codes(check([bad])), location
            assert 'lineage.column' not in codes(check([bad], available=False)), location
        bad = deepcopy(entity); bad['expression']['entity_filters'][0]['having'][0]['measure'] = 'SELECT count(*)'
        assert 'expression.invalid' in codes(check([bad]))
        inherited = deepcopy(ratio)
        inherited['expression']['entity_filters'] = deepcopy(entity['expression']['entity_filters'])
        assert not check([base, inherited]).errors
        bad = deepcopy(entity); bad['expression']['entity_filters'][0]['having'][0]['measure'] = 'metric(missing)'
        assert 'reference.missing' in codes(check([bad]))
        bad['expression']['entity_filters'][0]['having'][0]['measure'] = 'metric(multi)'
        assert 'graph.cycle' in codes(check([bad]))
        outer = deepcopy(ratio); outer['name'] = 'outer'; outer['expression']['measure'] = 'metric(ratio) * 100'
        assert not check([base,ratio,outer]).errors
        outer['expression']['mandatory_filters'] = [{'field':'missing','op':'='}]
        assert 'lineage.column' in codes(check([base,ratio,outer]))
        second = deepcopy(base); second['name'] = 'second'; second['lineage'][0]['models'] = ['other']
        second['expression']['mandatory_filters'] = []
        manifest['nodes']['model.test.other'] = {'resource_type':'model','name':'other','columns':{'source_system':{}}}
        outer['expression']['measure'] = 'metric(base) / metric(second)'
        outer['expression']['mandatory_filters'] = [{'field':'linked_date','op':'is_null'}]
        assert 'lineage.column' in codes(check([base,second,outer]))
    print('test_expressions: OK')


if __name__ == '__main__':
    run()
