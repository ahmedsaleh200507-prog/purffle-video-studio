from types import SimpleNamespace
import threading
import time
import pytest
from footage_search import discover
from scene_relevance import metadata_evidence, search_queries, suitability
from visual_director import build_contract, metadata_allows


def test_parallel_providers_before_alternative_queries():
    barrier=threading.Barrier(2)
    class Registry:
        def search(self, source, query):
            barrier.wait(timeout=2)
            return [SimpleNamespace(key=source)]
    rows=list(discover(Registry(), ['one','two'], ['exact','alias'], time.monotonic()+5))
    assert {(s,len(c)) for s,c in rows[:2]} == {('one',1),('two',1)}
    assert {(s,len(c)) for s,c in rows[2:]} == {('one',0),('two',0)}


def test_bad_provider_does_not_stop_other_source():
    class Registry:
        def search(self, source, query):
            if source=='bad': raise RuntimeError('credential must not be printed')
            return [SimpleNamespace(key='ok')]
    assert sorted(len(c) for _,c in discover(Registry(),['bad','good'],['lava'],time.monotonic()+2)) == [0,1]


def test_expired_budget_never_queries():
    assert list(discover(None,['one'],['lava'],time.monotonic()-1)) == []


@pytest.mark.parametrize('narration', ['Lava meets ice. The ice melts.', 'Lava trifft auf Eis. Das Eis schmilzt.'])
def test_lava_ice_does_not_become_ordinary_volcano(narration):
    plan=dict(narration=narration,object='lava',action='flowing',visual_search_query='lava ice contact')
    contract=build_contract(plan,'What Happens When Lava Meets Ice?',1)
    assert len(contract['sentence_needs']) == 2
    assert contract['family']=='lava_ice_contact'
    assert all('lava' in q for q in contract['queries'])
    assert metadata_evidence(plan,'lava volcano mountain',contract)['contradictions']
    assert not metadata_evidence(plan,'Lava flowing over glacier ice',contract)['contradictions']


def test_later_spoken_event_cannot_hide_behind_first_sentence():
    plan=dict(narration='The volcano stands tall. Then it erupts with an ash plume.',object='volcano',
              action='ambient',visual_search_query='volcano landscape')
    c=build_contract(plan,'Why do volcanoes erupt?',2)
    assert c['sentence_contracts'][1]['event_required']
    assert not metadata_allows(c,'peaceful mountain')
    assert metadata_allows(c,'volcano eruption ash plume')


def test_german_query_translation_and_uncertainty():
    p=dict(object='Gletscher',action='ambient',visual_search_query='Gletscher Eis',location='')
    assert 'glacier ice' in search_queries(p)
    e=metadata_evidence(p,'glacier ice')
    assert e['score']==1 and e['visual_proof'] is False
    r=suitability(e,{'visual_score':.3},{'width':1920,'height':1080})
    assert 'uncalibrated' in r['reliability']
