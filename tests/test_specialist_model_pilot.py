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

def test_narration_rejects_wrappers_and_out_of_range():
    from specialist_model_pilot import validate_narration_output
    with pytest.raises(ValueError,match="non_narration_wrapper"):
        validate_narration_output("<thought>not narration</thought> A story.", "en")
    with pytest.raises(ValueError,match="word_count"):
        validate_narration_output("A story.", "en")
    with pytest.raises(ValueError,match="non_narration_format"):
        validate_narration_output("# Introduction\nA story.", "en")
    text=("A heavy steel block sinks in water, but a ship made of steel can float. "
          "The difference lies in the shape of the hull. Its hollow interior lets the ship displace enough water to balance its weight. "
          "When cargo is loaded, the ship settles deeper into the water until the forces balance again.")
    assert validate_narration_output(text,"en")["detected_language"]=="en"

def test_native_top_ten_only_final_text_and_no_paid_fallback():
    from specialist_model_pilot import native_top_ten_request,ModelError
    seen=[]
    class Reply:
        status_code=200
        def json(self):
            return {"candidates":[{"finishReason":"STOP","content":{"parts":[
                {"text":"not final","thought":True},{"text":"Final narration."}]}}]}
    def post(url,**kwargs):
        seen.append((url,kwargs["json"]))
        return Reply()
    env={"GEMINI_API_KEY":"fake"}
    assert native_top_ten_request("gemini-3.8-flash","prompt",env,post=post)=="Final narration."
    assert seen[0][0].endswith("/gemini-3.8-flash:generateContent")
    assert seen[0][1]["generationConfig"]["thinkingConfig"]["thinkingLevel"]=="LOW"
    assert "tools" not in seen[0][1]
    with pytest.raises(ValueError):
        native_top_ten_request("gemini-4-argon","prompt",env,post=post)
    assert len(seen)==1

def test_native_top_ten_truncation_is_not_success():
    from specialist_model_pilot import native_top_ten_request,ModelError
    class Reply:
        status_code=200
        def json(self):
            return {"candidates":[{"finishReason":"MAX_TOKENS","content":{"parts":[{"text":"unfinished"}]}}]}
    with pytest.raises(ModelError) as exc:
        native_top_ten_request("gemini-4-hydrogen","prompt",{"GEMINI_API_KEY":"fake"},post=lambda *a,**k:Reply())
    assert exc.value.detail=="native_finish_MAX_TOKENS"
