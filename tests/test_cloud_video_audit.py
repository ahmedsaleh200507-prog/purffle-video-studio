import pytest
from cloud_video_audit import configured,request,native_payload,AuditError

def test_guard_prevents_any_network_call(tmp_path):
    def forbidden(*a,**kw):
        pytest.fail("unexpected network request")
    with pytest.raises(AuditError):
        request("gemini","gemini-4-hydrogen",tmp_path/"x",{"GEMINI_API_KEY":"test"},post=forbidden)
    assert not configured("gemini",{"GEMINI_API_KEY":"test","PURFFLE_GEMINI_FREE_CONFIRMED":"0"})

def test_disallow_unlisted_model(tmp_path):
    with pytest.raises(ValueError):
        request("gemini","gemini-4-neon",tmp_path/"x",{})

def test_native_mp4_and_no_paid_tools(tmp_path):
    p=tmp_path/"clip.mp4"
    p.write_bytes(b"test")
    data=native_payload(p)
    assert data["contents"][0]["parts"][0]["inlineData"]["mimeType"]=="video/mp4"
    assert "tools" not in data
    assert data["generationConfig"]["maxOutputTokens"]==2048

def test_exact_model_and_single_request(tmp_path):
    p=tmp_path/"clip.mp4"
    p.write_bytes(b"test")
    calls=[]
    class Response:
        status_code=503
    def post(url,**kw):
        calls.append(url)
        return Response()
    with pytest.raises(AuditError,match="HTTP_503"):
        request("gemini","gemini-4-hydrogen",p,{"GEMINI_API_KEY":"test","PURFFLE_GEMINI_FREE_CONFIRMED":"1"},post=post)
    assert len(calls)==1 and "gemini-4-hydrogen" in calls[0]


def test_groq_vision_maximum_three_frames(monkeypatch):
    from PIL import Image
    import media_validation
    from cloud_video_audit import frame_payload
    times=[]
    def frame(path,t,*args,**kwargs):
        times.append(t)
        return Image.new("RGB",(16,16))
    monkeypatch.setattr(media_validation,"_frame",frame)
    payload=frame_payload("fixture.mp4","qwen/qwen3.8-27b")
    parts=payload["messages"][0]["content"]
    assert len([p for p in parts if p["type"]=="image_url"])==3
    assert times==[.1,1.6,3.1]
    assert payload["response_format"]=={"type":"json_object"}
