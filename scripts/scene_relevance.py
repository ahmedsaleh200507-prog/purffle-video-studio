"""Small CPU-only lexical planner; metadata evidence is NOT visual proof.

Original implementation. No NLP/model download. Known German visual words map
into English stock vocabulary; unknown text retains the writer's English plan.
CLIP continues to independently screen the used frames before acceptance.
"""
import re
from topic_footage import GERMAN_FILMABLE

_TRANSLATE = {**GERMAN_FILMABLE, 'eis': 'ice', 'gletscher': 'glacier',
    'vulkan': 'volcano', 'vulkane': 'volcano', 'lavastrom': 'lava flow',
    'schnee': 'snow', 'meer': 'ocean', 'ozean': 'ocean', 'wasser': 'water',
    'blitz': 'lightning', 'blitze': 'lightning', 'himmel': 'sky',
    'wolken': 'clouds', 'fließt': 'flowing', 'fliesst': 'flowing',
    'schmilzt': 'melting', 'trifft': 'meets', 'auf': 'on'}


def english(value):
    return ' '.join(_TRANSLATE.get(w.casefold(), w.casefold())
                    for w in re.findall(r"[\w'-]+", str(value)))


def sentence_needs(narration, subject, base):
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', narration) if s.strip()]
    result = []
    for index, text in enumerate(sentences, 1):
        translated = english(text)
        interaction = (bool(re.search(r'\blava\b', translated))
                       and bool(re.search(r'\b(?:ice|glacier|snow)\b', translated))
                       and bool(re.search(r'\b(?:meet\w*|hit\w*|contact\w*|interact\w*|melt\w*|touch\w*|on|onto|over)\b', translated)))
        result.append({'sentence': index, 'text': text, 'subject': subject,
                       'english_query': 'lava ice contact' if interaction else english(base),
                       'interaction': 'lava_ice' if interaction else None,
                       'scope': 'visible subject illustration; causal claims are not visually proven'})
    return result


def search_queries(plan, contract=None):
    if contract:
        queries = list(contract.get('queries', []))
    else:
        queries = [plan['visual_search_query']]
    subject = english(plan['object'])
    action = english(plan.get('action', ''))
    location = english(plan.get('location', ''))
    queries += [english(q) for q in list(queries)]
    queries += [f'{subject} {action}', f'{subject} {location}', subject]
    if 'droplet' in subject or 'water drop' in subject:
        queries[1:1] = ['water droplets sunlight', 'water drops in sunlight', 'sunlight reflecting on water', 'water drops close up']
    return list(dict.fromkeys(re.sub(r'\s+', ' ', q).strip()[:120]
                             for q in queries if q.strip()))[:6]


def metadata_evidence(plan, text, contract=None):
    from media_validation import _documentary_metadata_terms
    have = _documentary_metadata_terms(english(text))
    required = _documentary_metadata_terms(english(plan['object']))
    matched = sorted(required & have)
    missing = sorted(required - have)
    contradictions = []
    needs = (contract or {}).get('sentence_needs', [])
    if any(n.get('interaction') == 'lava_ice' for n in needs):
        if not re.search(r'\blava\b', english(text)) or not re.search(
                r'\b(?:ice|glacier|snow)\b', english(text)):
            contradictions.append('lava–ice interaction requires both visible subjects in source metadata')
    return {'method': 'lexical_subject_coverage', 'matched_terms': matched,
            'missing_terms': missing, 'score': round(len(matched)/max(1, len(required)), 4),
            'contradictions': contradictions, 'visual_proof': False}


def suitability(evidence, match, quality):
    # Audit score, never a probability. Eligibility still requires ALL gates.
    visual = max(0., min(1., float(match.get('visual_score', 0))))
    score = round(100 * (.3 * evidence.get('score', 0) + .7 * visual), 2)
    return {'score': score, 'scale': '0–100 ranking index; not probability',
            'reasons': {'metadata': evidence, 'clip_cosine': visual,
                        'native_resolution': [quality['width'], quality['height']],
                        'motion': quality.get('motion_score')},
            'reliability': 'uncalibrated heuristic; sampled frames may miss brief actions; cannot prove causality',
            'accepted_by': 'independent metadata, license, FFprobe, motion and CLIP gates'}
