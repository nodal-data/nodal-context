"""ACF 0.2 grammar, recursive filters, reference graphs and lineage behavior."""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.ci'))
import validate


def run():
    import yaml
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schemas = [json.loads(p.read_text()) for p in (ROOT / 'schemas').glob('*.json')]
    registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in schemas)
    metric_schema = next(s for s in schemas if s['title'] == 'ACF Metric')
    ir_schema = next(s for s in schemas if s['title'] == 'ACF Question IR')
    mv = Draft202012Validator(metric_schema, registry=registry)
    iv = Draft202012Validator(ir_schema, registry=registry)
    for measure in ['SUM(amount) / COUNT(DISTINCT customer_id)', 'COUNT(*)',
                    '-(AVG(amount) + 1.5e2) * metric(base)', 'MIN(t.amount) - MAX(t.amount)',
                    'metric(with-hyphens) / 100', 'COUNT(distinct customer_id)']:
        validate.MeasureParser(measure).parse()
    for measure in ['amount', 'SUM(amount) FROM fact', 'COUNT(*) OVER ()',
                    'SUM(CASE WHEN x THEN 1 END)', 'SUM(x + y)', 'SUM(SUM(x))',
                    'metric(base); DROP TABLE t', 'metric(base) extra', '1 2',
                    'COUNT(DISTINCT *)', 'SUM(*)', 'COUNT(1)', 'ABS(SUM(x))',
                    'SUM(x) -- comment', '<as_of_date>', '', 'SUM(x) +', 'metric()']:
        try:
            validate.MeasureParser(measure).parse()
        except ValueError:
            pass
        else:
            raise AssertionError(f'accepted invalid measure: {measure}')

    group = {'any_of': [{'field': 'customer_id', 'op': 'is_null'},
                       {'all_of': [{'field': 'linked_date', 'op': '>', 'value': '<as_of_date>'}]}],
             'reason': 'Preserve unresolved-at-date aliases.'}
    base = {'name': 'base', 'definition': 'Observed aliases.', 'status': 'confirmed',
            'grain': 'alias', 'lineage': [{'source': 'dbt', 'models': ['identity']}],
            'expression': {'measure': 'COUNT(*)', 'mandatory_filters': [group],
                           'allowed_dimensions': ['source_system']}}
    ratio = {'name': 'ratio', 'definition': 'Ratio.', 'status': 'draft', 'grain': 'alias',
             'expression': {'measure': 'metric(base) / metric(base)',
                            'allowed_dimensions': ['source_system']}}
    entity = copy.deepcopy(base)
    entity['name'] = 'multi'
    entity['expression']['measure'] = 'COUNT(DISTINCT customer_id)'
    entity['expression']['entity_filters'] = [{'entity': 'customer_id', 'having': [
        {'measure': 'COUNT(DISTINCT source_system)', 'op': '>=', 'value': 2}]}]
    doc = {'metrics': [base, ratio, entity]}
    assert mv.is_valid(doc)
    assert iv.is_valid({'metric': 'base', 'filters': [group]})
    for bad in [{'any_of': []}, {'all_of': []}, {'any_of': [group], 'all_of': [group]},
                {'any_of': [group], 'field': 'x', 'op': '='},
                {'any_of': [{'field': 'x'}]}, {'field': 'x', 'op': '=', 'sql': 'x=1'}]:
        bad_doc = copy.deepcopy(doc)
        bad_doc['metrics'][0]['expression']['mandatory_filters'] = [bad]
        assert not mv.is_valid(bad_doc), bad
        assert not iv.is_valid({'metric': 'base', 'filters': [bad]}), bad
    bad_doc = copy.deepcopy(doc)
    del bad_doc['metrics'][1]['grain']
    assert not mv.is_valid(bad_doc)
    bad_doc = copy.deepcopy(doc)
    bad_doc['metrics'][2]['expression']['entity_filters'][0]['having'] = []
    assert not mv.is_valid(bad_doc)

    manifest = {'nodes': {'model.test.identity': {'resource_type': 'model', 'name': 'identity',
        'unique_id': 'model.test.identity', 'columns': {k: {} for k in
            ['customer_id', 'linked_date', 'source_system']}}}}
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'metrics.yaml'
        def check(metrics, available=True):
            path.write_text(yaml.safe_dump({'metrics': metrics}))
            return validate.expression_checks([(path, 'metric')], yaml,
                                              {'dbt': manifest} if available else {})
        errors, warnings = check([base, ratio, entity])
        assert not errors, errors
        assert len(warnings) == 3, warnings
        assert not check([base, ratio, entity], available=False)[0]
        # Legacy column aggregates retain the lineage requirement outside schema.
        for measure in ['COUNT(*)', 'SUM(customer_id)', '1']:
            bad = copy.deepcopy(ratio)
            bad['expression']['measure'] = measure
            assert any('require lineage' in e for e in check([bad])[0])
        bad = copy.deepcopy(ratio)
        bad['expression']['measure'] = 'metric(missing)'
        assert any('not defined' in e for e in check([base, bad])[0])
        prose = copy.deepcopy(base)
        del prose['expression']
        assert any('no expression' in e for e in check([prose, ratio])[0])
        assert any('duplicate metric' in e for e in check([base, base])[0])
        bad = copy.deepcopy(ratio)
        bad['expression']['measure'] = 'metric(ratio)'
        assert any('cyclic' in e for e in check([bad])[0])
        a, b = copy.deepcopy(ratio), copy.deepcopy(ratio)
        a['name'], b['name'] = 'a', 'b'
        a['expression']['measure'], b['expression']['measure'] = 'metric(b)', 'metric(a)'
        assert any('cyclic' in e for e in check([a, b])[0])
        bad = copy.deepcopy(ratio)
        bad['expression']['allowed_dimensions'] = ['linked_date']
        assert any('subset' in e for e in check([base, bad])[0])
        unspecified = copy.deepcopy(base)
        del unspecified['expression']['allowed_dimensions']
        assert any('enumerated' in e for e in check([unspecified, ratio])[0])
        for location in ['entity', 'having', 'measure', 'filter']:
            bad = copy.deepcopy(entity)
            expr = bad['expression']
            if location == 'entity':
                expr['entity_filters'][0]['entity'] = 'missing'
            elif location == 'having':
                expr['entity_filters'][0]['having'][0]['measure'] = 'COUNT(DISTINCT missing)'
            elif location == 'measure':
                expr['measure'] = 'SUM(identity.missing)'
            else:
                expr['mandatory_filters'][0]['any_of'][1]['all_of'][0]['field'] = 'missing'
            assert any("column" in e and 'missing' in e for e in check([bad])[0]), location
            assert not check([bad], available=False)[0]
        bad = copy.deepcopy(entity)
        bad['expression']['entity_filters'][0]['having'][0]['measure'] = 'SELECT count(*)'
        assert any('invalid measure' in e for e in check([bad])[0])
        inherited_entity = copy.deepcopy(ratio)
        inherited_entity['expression']['entity_filters'] = copy.deepcopy(
            entity['expression']['entity_filters'])
        assert not check([base, inherited_entity])[0]
        # References in having participate in cycle and existence checks too.
        bad = copy.deepcopy(entity)
        bad['expression']['entity_filters'][0]['having'][0]['measure'] = 'metric(missing)'
        assert any('not defined' in e for e in check([bad])[0])
        bad['expression']['entity_filters'][0]['having'][0]['measure'] = 'metric(multi)'
        assert any('cyclic' in e for e in check([bad])[0])
        # Transitive reference lineage, including own filter overlays on every leaf.
        outer = copy.deepcopy(ratio)
        outer['name'] = 'outer'
        outer['expression']['measure'] = 'metric(ratio) * 100'
        assert not check([base, ratio, outer])[0]
        outer['expression']['mandatory_filters'] = [{'field': 'missing', 'op': '='}]
        assert any('missing' in e for e in check([base, ratio, outer])[0])
        second = copy.deepcopy(base)
        second['name'] = 'second'
        second['lineage'][0]['models'] = ['other']
        second['expression']['mandatory_filters'] = []
        manifest['nodes']['model.test.other'] = {'resource_type': 'model', 'name': 'other',
                                               'columns': {'source_system': {}}}
        outer['expression']['measure'] = 'metric(base) / metric(second)'
        outer['expression']['mandatory_filters'] = [{'field': 'linked_date', 'op': 'is_null'}]
        assert any('linked_date' in e for e in check([base, second, outer])[0])
        # The CLI must run semantic checks and leave malformed-schema reporting intact.
        path.write_text(yaml.safe_dump({'metrics': [ratio]}))
        assert validate.main([td, '--schemas', str(ROOT / 'schemas')]) == 1
        path.write_text(yaml.safe_dump({'metrics': [base, ratio, entity]}))
        mp = Path(td) / 'manifest.json'
        mp.write_text(json.dumps(manifest))
        assert validate.main([td, '--schemas', str(ROOT / 'schemas'), '--manifest', f'dbt={mp}']) == 0
        path.write_text('metrics: [{name: x, expression: []}]')
        assert validate.main([td, '--schemas', str(ROOT / 'schemas')]) == 1
    print('test_expressions: OK')


if __name__ == '__main__':
    run()
