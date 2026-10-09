"""Portable lexical retrieval artifacts for a tiny, fictional Korean policy corpus.

Character TF-IDF + cosine is deliberately inspectable. It is not a neural model,
LLM generation, real banking policy, or a representative search-quality benchmark.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
import re
import time

import numpy as np

SCOPE = 'fictional corpus; character TF-IDF cosine search; warm local queries; not LLM or bank SLA'
QUERIES = [
    ('하루 이체 한도', 'transfer'), ('송금 본인 인증', 'transfer'),
    ('해외 결제 취소 환불', 'refund'), ('환불 처리 기간', 'refund'),
    ('분실 카드 재발급', 'card'), ('카드 분실 신고', 'card'),
    ('대출 소득 증빙 서류', 'loan'), ('대출 심사 제출 서류', 'loan'),
]


def initial_sources():
    rows = [
        ('transfer', '이체 한도 안내', '하루 이체 한도는 300만 원입니다. 한도 상향을 위한 송금 본인 인증은 앱에서 진행합니다.'),
        ('refund', '해외 결제 취소와 환불', '해외 결제 취소 후 환불 처리 기간은 접수일로부터 3영업일입니다. 접수 번호로 진행 상황을 확인합니다.'),
        ('card', '분실 카드 신고와 재발급', '카드 분실 신고 시 결제가 즉시 정지됩니다. 분실 카드 재발급은 앱에서 신청하며 새 배송지를 확인합니다.'),
        ('loan', '대출 심사 제출 서류', '대출 심사에는 소득 증빙 서류와 재직 확인 서류를 제출합니다. 발급일로부터 30일 이내의 서류를 사용합니다.'),
    ]
    return {sid: dict(source_id=sid, title=title, text=text, revision=1, deleted=False) for sid, title, text in rows}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def grams(text):
    text = re.sub(r'\s+', ' ', text.lower()).strip()
    return Counter(text[i:i+n] for n in (2, 3, 4) for i in range(len(text)-n+1))


def encode(model, text):
    counts = grams(text)
    vector = np.array([counts.get(token, 0) * weight for token, weight in zip(model['vocabulary'], model['idf'])], dtype=float)
    if model['encoder'] == 'collapsed':
        # Explicit fault: discard query/document distinctions. Scores are still
        # computed, and the evaluation catches the resulting tied rankings.
        vector = np.ones_like(vector)
    if model['coordinates'] == 'reverse':
        vector = vector[::-1]
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def build_artifact(sources, variant='paired'):
    if variant not in ('baseline', 'paired', 'mismatch', 'regressed'):
        raise ValueError('unknown candidate')
    docs = [deepcopy(source) for _, source in sorted(sources.items()) if not source['deleted']]
    token_sets = [set(grams(d['title'] + ' ' + d['text'])) for d in docs]
    vocabulary = sorted(set().union(*token_sets)) if docs else []
    model = dict(vocabulary=vocabulary, idf=[math.log((1 + len(docs)) / (1 + sum(t in s for s in token_sets))) + 1 for t in vocabulary],
                 coordinates='forward' if variant == 'baseline' else 'reverse',
                 encoder='collapsed' if variant == 'regressed' else 'tfidf', format='char-tfidf-2-4-v1')
    index_model = deepcopy(model)
    if variant == 'mismatch':
        index_model['coordinates'] = 'forward'
    index = dict(model_hash=digest(index_model), documents=docs,
                 vectors=[encode(index_model, d['title'] + ' ' + d['text']).tolist() for d in docs])
    artifact = dict(model=model, model_hash=digest(model), index=index, corpus_hash=digest(sources))
    return dict(artifact, artifact_hash=digest(artifact))


def compatible(artifact):
    try:
        payload = {k: v for k, v in artifact.items() if k != 'artifact_hash'}
        return (artifact['artifact_hash'] == digest(payload)
                and artifact['model_hash'] == digest(artifact['model'])
                and artifact['model_hash'] == artifact['index']['model_hash'])
    except (ValueError, KeyError, TypeError):
        return False


def retrieve(artifact, query, *, enforce=True):
    if enforce and not compatible(artifact):
        raise ValueError('model_index_mismatch')
    if not query.strip() or not artifact['index']['documents']:
        return []
    scores = np.asarray(artifact['index']['vectors']) @ encode(artifact['model'], query)
    return [dict(artifact['index']['documents'][int(i)], similarity=float(scores[i]))
            for i in np.argsort(-scores, kind='stable') if scores[i] > 0][:2]


def gates(match, recall, baseline, p95, count):
    failures = []
    if not match:
        failures.append('model_index_match')
    if not count or not math.isfinite(recall) or recall < .90:
        failures.append('retrieval_quality')
    if not math.isfinite(baseline) or not math.isfinite(recall) or baseline - recall > .05:
        failures.append('quality_regression')
    if not count or not math.isfinite(p95) or p95 > 50:
        failures.append('query_latency')
    return failures


def evaluate_release(sources, candidate):
    artifact = build_artifact(sources, candidate)
    baseline = build_artifact(sources, 'baseline')
    fixtures = [(query, sid) for query, sid in QUERIES if not sources[sid]['deleted']]
    base_correct = sum(bool(hits := retrieve(baseline, q)) and hits[0]['source_id'] == sid for q, sid in fixtures)
    baseline_recall = base_correct / len(fixtures) if fixtures else 0.
    for query, _ in fixtures:
        retrieve(artifact, query, enforce=False)  # warmup; excluded from reported samples
    samples = []
    for _ in range(3):
        for query, expected in fixtures:
            start = time.perf_counter_ns()
            hits = retrieve(artifact, query, enforce=False)
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            samples.append(dict(query=query, expected_source=expected,
                                actual_source=hits[0]['source_id'] if hits else None, latency_ms=elapsed))
    recall = sum(s['actual_source'] == s['expected_source'] for s in samples) / len(samples) if samples else 0.
    p95 = sorted(s['latency_ms'] for s in samples)[math.ceil(len(samples) * .95) - 1] if samples else 0.
    failures = gates(compatible(artifact), recall, baseline_recall, p95, len(samples))
    return dict(candidate=candidate, passed=not failures, failed_gates=failures,
                recall_at_1=recall, baseline_recall_at_1=baseline_recall, p95_ms=p95,
                sample_count=len(samples), samples=samples, artifact=artifact,
                model_index_match=compatible(artifact), scope=SCOPE,
                thresholds=dict(min_recall_at_1=.9, max_recall_drop=.05, max_warm_p95_ms=50))
