import pytest
from openrouter_writer_benchmark import WRITERS,CASES,MAX_WRITER_CALLS,writer_prompt
from specialist_model_pilot import request,ModelError

def test_only_explicit_free_writers_and_bounded_budget():
    assert len(WRITERS)==4
    assert all(m.endswith(":free") for m in WRITERS)
    assert len(CASES)==5 and len(WRITERS)*len(CASES)*2==MAX_WRITER_CALLS
    assert "German" in writer_prompt("Topic","de","sources")

def test_429_single_attempt_never_retries():
    calls=[]
    class Reply:
        status_code=429
    def post(*args,**kwargs):
        calls.append(kwargs["json"])
        return Reply()
    def no_sleep(_):
        pytest.fail("must not retry")
    env={"OPENROUTER_API_KEY":"fake","PURFFLE_OPENROUTER_FREE_CONFIRMED":"1"}
    with pytest.raises(ModelError) as exc:
        request("openrouter",WRITERS[0],[],env,post=post,sleep=no_sleep,attempts=1)
    assert exc.value.status_code==429 and len(calls)==1
    assert calls[0]["provider"]["max_price"]["completion"]==0
