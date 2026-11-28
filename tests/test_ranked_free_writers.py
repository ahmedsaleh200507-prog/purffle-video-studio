import json
import pytest
from types import SimpleNamespace
from cloud_model_router import Router,ModelError
from story_room import StoryRoom
from story_first import RANKED_WRITERS,TEXT_SCHEMA,writer_preferences,QWEN_REVIEWERS

NEMOTRON=RANKED_WRITERS[0]
GOOD="A solid piece of steel sinks, but a ship made of the same material floats. Its hollow hull gives it enough volume to displace water equal to its weight. As cargo comes aboard, the ship settles deeper until the water pushes back with enough force to balance the new weight."
def reply(code=200,content=GOOD):
    return SimpleNamespace(status_code=code,json=lambda:{"choices":[{"finish_reason":"stop","message":{"content":content}}]})

def test_nemotron_first_and_zero_price(monkeypatch):
    monkeypatch.setenv("PURFFLE_RANKED_WRITERS","1")
    calls=[]
    def post(url,**kw):
        calls.append(kw["json"])
        return reply()
    r=Router({"PURFFLE_RANKED_WRITERS":"1","PURFFLE_OPENROUTER_FREE_CONFIRMED":"1","OPENROUTER_API_KEY":"test","GROQ_API_KEY":"test"},post)
    data,model=StoryRoom(r).ask("writer","story",TEXT_SCHEMA,writer_preferences())
    assert model==NEMOTRON and data["narration"]==GOOD
    assert len(calls)==1 and calls[0]["model"].endswith(":free")
    assert calls[0]["provider"]["max_price"]["completion"]==0

def test_nemotron_rate_limit_falls_through_to_qwen(monkeypatch):
    monkeypatch.setenv("PURFFLE_RANKED_WRITERS","1")
    calls=[]
    def post(url,**kw):
        calls.append(kw["json"]["model"])
        return reply(429) if len(calls)==1 else reply(content=json.dumps({"narration":GOOD}))
    r=Router({"PURFFLE_RANKED_WRITERS":"1","PURFFLE_OPENROUTER_FREE_CONFIRMED":"1","OPENROUTER_API_KEY":"test","GROQ_API_KEY":"test"},post)
    room=StoryRoom(r)
    data,model=room.ask("writer","story",TEXT_SCHEMA,writer_preferences())
    assert calls==[NEMOTRON,RANKED_WRITERS[1]] and model==RANKED_WRITERS[1]
    assert room.trace[0]["status"]=="http_or_json_429"

def test_free_confirmation_and_role_separation(monkeypatch):
    monkeypatch.setenv("PURFFLE_RANKED_WRITERS","1")
    r=Router({"PURFFLE_RANKED_WRITERS":"1","OPENROUTER_API_KEY":"test"})
    assert not r.keys["openrouter"]
    r=Router({"PURFFLE_RANKED_WRITERS":"1","PURFFLE_OPENROUTER_FREE_CONFIRMED":"1","OPENROUTER_API_KEY":"test"})
    with pytest.raises(ModelError):
        r.request("openrouter","paid/model",messages=[],schema=TEXT_SCHEMA)
    with pytest.raises(ModelError):
        r.request("openrouter",NEMOTRON,messages=[],schema={"type":"object"})
    with pytest.raises(RuntimeError):
        StoryRoom(r).ask("review","check",TEXT_SCHEMA,QWEN_REVIEWERS)

def test_ranked_invalid_output_rejected(monkeypatch):
    monkeypatch.setenv("PURFFLE_RANKED_WRITERS","1")
    r=Router({"PURFFLE_RANKED_WRITERS":"1","PURFFLE_OPENROUTER_FREE_CONFIRMED":"1","OPENROUTER_API_KEY":"test"},lambda *a,**kw:reply(content="<thought>draft</thought>"+GOOD))
    with pytest.raises(ModelError) as exc:
        r.request("openrouter",NEMOTRON,messages=[],schema=TEXT_SCHEMA)
    assert exc.value.status_code==422
