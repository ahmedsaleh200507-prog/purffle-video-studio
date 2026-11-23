"""Offline tests: optional no-cost Google Gemini script API."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from long_llm import GEMINI_MODEL, GEMINI_URL, LongLLM, LongLLMResponseError, LongLLMUnavailable, get_long_client

class TooManyRequests(Exception):
    status_code = 429
class Unauthorized(Exception):
    status_code = 401
class FakeGroq:
    def __init__(self, outcome):
        self.calls=0
        self.outcome=outcome
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self,**kwargs):
        self.calls+=1
        if isinstance(self.outcome,Exception): raise self.outcome
        return self.outcome
class FakeResponse:
    def __init__(self,status=200,text='{"chapters":[]}'):
        self.status_code=status
        self.body={"choices":[{"finish_reason":"stop","message":{"content":text}}]}
    def json(self):
        return self.body
def prompt():
    return {"model":"openai/gpt-oss-20b",
            "messages":[{"role":"system","content":"Return JSON only"},{"role":"user","content":"Write a chapter"}],
            "response_format":{"type":"json_schema","json_schema":{
                "name":"documentary_chapters","strict":True,
                "schema":{"type":"object","properties":{"chapters":{"type":"array","items":{"type":"object"}}}}}},
            "max_tokens":2000,"temperature":.2}

def test_groq_429_routes_same_json_request_to_free_gemini():
    original=prompt()
    calls=[]
    def post(url,headers,json,timeout):
        calls.append((url,headers,json,timeout))
        return FakeResponse()
    api=LongLLM(groq=FakeGroq(TooManyRequests("quota")),gemini_key="TEST_ONLY_VALUE",post=post)
    result=api.chat.completions.create(**original)
    assert json.loads(result.choices[0].message.content)=={"chapters":[]}
    assert len(calls)==1
    url,headers,body,timeout=calls[0]
    assert url==GEMINI_URL and url.startswith("https://")
    assert headers["Authorization"]=="Bearer TEST_ONLY_VALUE"
    assert body["model"]==GEMINI_MODEL and body["messages"]==original["messages"]
    assert body["response_format"]["json_schema"]["schema"]==original["response_format"]["json_schema"]["schema"]
    assert "strict" not in body["response_format"]["json_schema"]
    assert "TEST_ONLY_VALUE" not in str(body)

def test_groq_success_never_uses_secondary_gemini():
    good=SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",message=SimpleNamespace(content='{"chapters":[]}'))])
    posts=[]
    groq=FakeGroq(good)
    cli=LongLLM(groq=groq,gemini_key="KEY",post=lambda *a,**kw:posts.append(kw))
    assert cli.chat.completions.create(**prompt()) is good
    assert groq.calls==1 and not posts

def test_auth_error_is_not_concealed():
    cli=LongLLM(groq=FakeGroq(Unauthorized("bad key")),gemini_key="KEY",post=lambda **kw:FakeResponse())
    with pytest.raises(Unauthorized): cli.chat.completions.create(**prompt())

def test_gemini_only_when_groq_key_missing():
    calls=[]
    cli=get_long_client(environ={"GEMINI_API_KEY":"FAKE"},post=lambda *a,**kw:(calls.append(kw) or FakeResponse()))
    cli.chat.completions.create(**prompt())
    assert len(calls)==1 and calls[0]["json"]["model"]==GEMINI_MODEL

def test_gemini_429_never_claims_success():
    cli=LongLLM(gemini_key="FAKE",post=lambda *a,**kw:FakeResponse(status=429))
    with pytest.raises(LongLLMResponseError,match="Gemini: HTTP 429"):
        cli.chat.completions.create(**prompt())

def test_no_keys_fail_before_any_model_work():
    with pytest.raises(LongLLMUnavailable,match="No long-video LLM key"):
        get_long_client(environ={})

def test_explicit_gemini_primary_conserves_groq():
    groq=FakeGroq(AssertionError("must not call Groq"))
    calls=[]
    cli=get_long_client(groq=groq,environ={"GEMINI_API_KEY":"FAKE","PURFFLE_LONG_LLM_PRIMARY":"gemini"},post=lambda *a,**kw:(calls.append(kw) or FakeResponse()))
    cli.chat.completions.create(**prompt())
    assert calls and groq.calls==0

def test_generated_invalid_groq_json_switches_to_gemini():
    class BadJSON(Exception):
        code="json_validate_failed"
        status_code=400
    calls=[]
    cli=LongLLM(groq=FakeGroq(BadJSON("Failed to validate JSON: json_validate_failed")),gemini_key="FAKE",post=lambda *a,**kw:(calls.append(kw) or FakeResponse()))
    cli.chat.completions.create(**prompt())
    assert len(calls)==1

def test_workflows_use_github_secrets_only():
    root=Path(__file__).resolve().parents[1]
    for path in ("videos.yml","long-batch.yml"):
        text=(root/".github"/"workflows"/path).read_text()
        assert ("GEMINI_API_KEY: $"+"{{ secrets.GEMINI_API_KEY }}") in text
        assert "actions/upload-artifact@" in text

def test_shorts_fallback_keeps_narrator_and_fact_and_visual_checks():
    root=Path(__file__).resolve().parents[1]
    render=(root/"scripts"/"render_job.py").read_text()
    runtime=(root/"scripts"/"studio_runtime.py").read_text()
    assert "fallbacks = ['groq']" in render and "llm_fallbacks=fallbacks" in render
    assert "gemini-3.1-flash-lite" in runtime
    assert "fixed Piper Joe/Thorsten required" in render
    assert "screen_narration(" in render
    assert "validate_result(" in render
    assert "visual_director_preflight" in render



def test_long_defaults_to_gemini_without_editing_github_variables():
    cli=get_long_client(
        groq=FakeGroq(AssertionError("Groq should be reserved")),
        environ={"GEMINI_API_KEY":"FAKE"},
        post=lambda *args,**kw:FakeResponse())
    assert cli.chat.completions.prefer == "gemini"
    assert cli.chat.completions.create(**prompt()).choices[0].finish_reason=="stop"


def test_gemini_429_switches_to_groq_and_stops_retrying_gemini_for_later_chapters():
    good=SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="stop",message=SimpleNamespace(content='{"chapters":[]}'))])
    groq=FakeGroq(good)
    seen=[]
    def post(*args,**kwargs):
        seen.append(kwargs)
        return FakeResponse(status=429)
    cli=LongLLM(groq=groq,gemini_key="FAKE",post=post,prefer="gemini")
    assert cli.chat.completions.create(**prompt()) is good
    assert cli.chat.completions.create(**prompt()) is good
    assert len(seen)==1 and groq.calls==2


def test_gemini_invalid_auth_does_not_silently_fall_back_to_groq():
    groq=FakeGroq(AssertionError("Never mask invalid Gemini credentials"))
    cli=LongLLM(groq=groq,gemini_key="FAKE",
                post=lambda *a,**kw:FakeResponse(status=401),
                prefer="gemini")
    with pytest.raises(LongLLMResponseError,match="Gemini: HTTP 401"):
        cli.chat.completions.create(**prompt())
    assert groq.calls==0


def test_gemini_schema_400_uses_one_json_mode_attempt_and_keeps_local_contract():
    payloads=[]
    def post(*args,**kwargs):
        payloads.append(kwargs["json"])
        return FakeResponse(status=400) if len(payloads)==1 else FakeResponse()
    cli=LongLLM(gemini_key="FAKE",post=post,prefer="gemini")
    assert cli.chat.completions.create(**prompt()).choices[0].finish_reason=="stop"
    assert len(payloads)==2
    assert payloads[0]["response_format"]["type"]=="json_schema"
    assert payloads[1]["response_format"]=={"type":"json_object"}


def test_long_variant_only_prefers_native_1080p_under_oversized_4k(monkeypatch):
    from video_sources import ProviderRegistry
    files=[
        {"url":"https://example.org/4k.mp4","file_type":"video/mp4",
         "width":3840,"height":2160,"file_size":245000000},
        {"url":"https://example.org/1080.mp4","file_type":"video/mp4",
         "width":1920,"height":1080,"file_size":64000000},
        {"url":"https://example.org/720.mp4","file_type":"video/mp4",
         "width":1280,"height":720,"file_size":25000000},
    ]
    monkeypatch.setenv("PURFFLE_LONG_STOCK_HD_VARIANTS","1")
    assert ProviderRegistry._files(files)["url"].endswith("/1080.mp4")
    monkeypatch.delenv("PURFFLE_LONG_STOCK_HD_VARIANTS",raising=False)
    assert ProviderRegistry._files(files)["url"].endswith("/4k.mp4")
