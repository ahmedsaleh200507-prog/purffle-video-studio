import pytest
from specialist_model_pilot import endpoint,parse_vision,vision_prompt,request

def test_provider_allowlist_and_confirmation():
    env={"OPENROUTER_API_KEY":"fake"}
    model="google/gemma-4-31b-it:free"
    assert endpoint("openrouter",model,env) is None
    env["PURFFLE_OPENROUTER_FREE_CONFIRMED"]="1"
    assert endpoint("openrouter",model,env).startswith("https://openrouter.ai/")
    with pytest.raises(ValueError):
        endpoint("openrouter","google/gemma-4-31b-it",env)

def test_cloudflare_requires_free_confirmation_and_account():
    env={"CLOUDFLARE_API_TOKEN":"fake","CLOUDFLARE_ACCOUNT_ID":"a"*32}
    model="@cf/qwen/qwen3.8-27b"
    assert endpoint("cloudflare",model,env) is None
    env["PURFFLE_CLOUDFLARE_FREE_CONFIRMED"]="1"
    assert endpoint("cloudflare",model,env).endswith("/ai/v1/chat/completions")

def test_vision_scores_reversed_questions_and_abstention():
    assert parse_vision('{"first":false,"second":true,"observation":"car"}',False)["correct"]==2
    assert parse_vision('{"first":true,"second":true,"observation":"both"}',True)["false_positive"]
    assert parse_vision('{"first":null,"second":false,"observation":"uncertain"}',True)["correct"]==1
    with pytest.raises(ValueError):
        parse_vision('{"first":"yes","second":false,"observation":"cat"}',True)
    assert vision_prompt("data:image/jpeg;base64,AAAA","cat","car")[0]["content"][0]["type"]=="image_url"

def test_openrouter_never_falls_back_to_paid_model():
    seen=[]
    class Reply:
        status_code=200
        def json(self):
            return {"choices":[{"finish_reason":"stop","message":{"content":"test output"}}]}
    def post(url,**kwargs):
        seen.append(kwargs["json"])
        return Reply()
    env={"OPENROUTER_API_KEY":"fake","PURFFLE_OPENROUTER_FREE_CONFIRMED":"1"}
    model="google/gemma-4-31b-it:free"
    assert request("openrouter",model,[],env,post=post)=="test output"
    assert seen[0]["model"]==model and seen[0]["provider"]["max_price"]["completion"]==0

def test_new_writers_are_text_only_and_free_variants():
    from specialist_model_pilot import NEW_WRITER_MODELS,CANDIDATES
    found={m for p,m,roles in CANDIDATES if m in NEW_WRITER_MODELS}
    assert found==NEW_WRITER_MODELS
    for provider,model,roles in CANDIDATES:
        if model in found:
            assert roles==("text",)
            assert provider=="gemini" or (provider=="openrouter" and model.endswith(":free"))
