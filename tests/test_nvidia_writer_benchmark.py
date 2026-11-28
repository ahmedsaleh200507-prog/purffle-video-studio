import pytest
from types import SimpleNamespace
from nvidia_writer_benchmark import WRITERS,MAX_WRITER_CALLS,CASES,configured,request,URL,ModelError

ENV={"NVIDIA_API_KEY":"fake","PURFFLE_NVIDIA_FREE_CONFIRMED":"1"}
def test_trial_budget_and_exact_model():
    assert len(WRITERS)*len(CASES)*2==MAX_WRITER_CALLS==30
    calls=[]
    def post(url,**kw):
        calls.append((url,kw))
        return SimpleNamespace(status_code=200,json=lambda:{"choices":[{"finish_reason":"stop","message":{"content":"Final text.","reasoning_content":"not final"}}]})
    assert request(WRITERS[0],"prompt",ENV,post=post)=="Final text."
    assert calls[0][0]==URL and calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["json"]["model"]==WRITERS[0]
    with pytest.raises(ValueError):
        request("other/model","prompt",ENV,post=post)
    with pytest.raises(ModelError):
        request(WRITERS[0],"prompt",{"NVIDIA_API_KEY":"fake"},post=post)
    assert len(calls)==1

@pytest.mark.parametrize("code",[402,429,503])
def test_no_retry_or_fallback(code):
    calls=[]
    def post(*a,**k):
        calls.append(1)
        return SimpleNamespace(status_code=code)
    with pytest.raises(ModelError) as exc:
        request(WRITERS[0],"prompt",ENV,post=post)
    assert exc.value.status_code==code and len(calls)==1
