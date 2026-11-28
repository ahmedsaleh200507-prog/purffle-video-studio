import pytest
from cloud_model_router import ModelError
from narration_model_benchmark import LockedWriter, exact_request, WRITERS

def test_locked_writer_never_substitutes():
    calls=[]
    class Router:
        def request(self,provider,model,**kwargs):
            calls.append(model)
            raise ModelError(404)
    with pytest.raises(ModelError):
        LockedWriter(Router(),WRITERS[0]).ask("writer","test",{},WRITERS)
    assert calls==[WRITERS[0]]

def test_same_model_retry_for_transient_quota():
    calls=[]
    sleeps=[]
    class Router:
        def request(self,provider,model,**kwargs):
            calls.append(model)
            if len(calls)==1:
                raise ModelError(429)
            return '{"narration":"real test response"}'
    result=exact_request(Router(),WRITERS[0],"test",{},temperature=.7,max_tokens=200,role="writer",sleep=sleeps.append)
    assert calls==[WRITERS[0],WRITERS[0]] and sleeps==[65]
    assert result["narration"]=="real test response"
