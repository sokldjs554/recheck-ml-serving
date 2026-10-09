"""A version-only check or fabricated evaluation score would fail these tests."""
import importlib.util
import copy
import math
import pytest


def module():
    assert importlib.util.find_spec('recheck.retrieval'), 'retrieval artifacts are not implemented'
    from recheck import retrieval
    return retrieval


def test_paired_artifacts_are_portable_reproducible_and_search_actual_text():
    r = module()
    import json
    sources = r.initial_sources()
    first = r.build_artifact(sources, 'paired')
    assert first == r.build_artifact(sources, 'paired')
    restored = json.loads(json.dumps(first))
    assert r.compatible(restored)
    hits = r.retrieve(restored, '하루 이체 한도')
    assert hits[0]['source_id'] == 'transfer'
    assert '300만 원' in hits[0]['text']
    sources['transfer']['text'] = '하루 이체 한도는 100만 원입니다.'
    sources['transfer']['revision'] += 1
    rebuilt = r.build_artifact(sources, 'paired')
    assert rebuilt['artifact_hash'] != first['artifact_hash']
    assert '100만 원' in r.retrieve(rebuilt, '하루 이체 한도')[0]['text']
    assert '300만 원' in r.retrieve(first, '하루 이체 한도')[0]['text']


def test_equal_dimension_model_index_mismatch_is_rejected():
    r = module()
    artifact = r.build_artifact(r.initial_sources(), 'mismatch')
    assert len(artifact['model']['idf']) == len(artifact['index']['vectors'][0])
    assert not r.compatible(artifact)
    with pytest.raises(ValueError, match='model_index_mismatch'):
        r.retrieve(artifact, '하루 이체 한도')
    report = r.evaluate_release(r.initial_sources(), 'mismatch')
    assert not report['passed']
    assert 'model_index_match' in report['failed_gates']


def test_quality_gate_uses_ranked_predictions_and_raw_measured_latencies():
    r = module()
    good = r.evaluate_release(r.initial_sources(), 'paired')
    assert good['passed']
    assert good['recall_at_1'] >= .9
    assert len(good['samples']) == 24
    assert all(s['latency_ms'] > 0 and math.isfinite(s['latency_ms']) for s in good['samples'])
    assert all(s['actual_source'] == s['expected_source'] for s in good['samples'])
    bad = r.evaluate_release(r.initial_sources(), 'regressed')
    assert not bad['passed']
    assert bad['recall_at_1'] < .9
    assert 'retrieval_quality' in bad['failed_gates']
    assert 'quality_regression' in bad['failed_gates']


def test_empty_corpus_and_empty_query_fail_closed():
    r = module()
    sources = r.initial_sources()
    for source in sources.values():
        source['deleted'] = True
    assert not r.evaluate_release(sources, 'paired')['passed']
    assert r.retrieve(r.build_artifact(r.initial_sources(), 'paired'), '     ') == []


def test_corrupted_artifact_and_nonfinite_or_slow_measurements_fail_closed():
    r = module()
    artifact = r.build_artifact(r.initial_sources(), 'paired')
    corrupt = copy.deepcopy(artifact)
    corrupt['index']['vectors'][0][0] += .5
    assert not r.compatible(corrupt)
    report = r.evaluate_release(r.initial_sources(), 'paired')
    for value in [float('nan'), float('inf'), 50.01]:
        assert 'query_latency' in r.gates(True, 1., 1., value, 24)
    assert r.gates(True, 1., 1., 50., 24) == []
    assert r.gates(True, 1., 1., 1., 0)
    assert report['artifact']['artifact_hash'] == r.build_artifact(r.initial_sources(), 'paired')['artifact_hash']
