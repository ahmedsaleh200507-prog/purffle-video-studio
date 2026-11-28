"""Bounded free-account video audition, independent of production.
Google gets native MP4 bytes; Groq gets ordered sampled images, not native video.
A free-capable model ID is not evidence that a particular account is unbilled.
"""
import base64
import io
import json
import os
import tempfile
import time
from pathlib import Path
from temporal_vision_pilot import prepare, prompt, score

MODELS=(
    ("gemini","gemini-4-hydrogen"),
    ("gemini","gemini-3.8-flash"),
    ("gemini","gemini-3.5-flash-lite"),
    ("groq","qwen/qwen3.8-27b"),
)
KEYS={"gemini":"GEMINI_API_KEY","groq":"GROQ_API_KEY"}
FLAGS={"gemini":"PURFFLE_GEMINI_FREE_CONFIRMED","groq":"PURFFLE_GROQ_FREE_CONFIRMED"}
class AuditError(Exception):
    pass

def configured(provider,env):
    return env.get(FLAGS[provider])=="1" and bool(env.get(KEYS[provider],"").strip())

def native_payload(path):
    data=path.read_bytes()
    if not data or len(data)>4*1024*1024:
        raise ValueError("video outside bounded inline size")
    return {"contents":[{"role":"user","parts":[
        {"inlineData":{"mimeType":"video/mp4","data":base64.b64encode(data).decode()}},
        {"text":prompt()}]}],
        "generationConfig":{"temperature":0.1,"maxOutputTokens":2048,"responseMimeType":"application/json"}}

def frame_payload(path,model):
    from media_validation import _frame
    parts=[]
    for t in (.1,1.6,3.1):
        frame=_frame(path,t,448,preserve_aspect=True)
        buf=io.BytesIO()
        frame.convert("RGB").save(buf,format="JPEG",quality=82)
        parts.append({"type":"text","text":f"Frame at {t:.1f} seconds"})
        parts.append({"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+base64.b64encode(buf.getvalue()).decode()}})
    parts.append({"type":"text","text":prompt()})
    return {"model":model,"messages":[{"role":"user","content":parts}],
            "temperature":0.1,"max_completion_tokens":1024,"stream":False,"reasoning_effort":"low",
            "response_format":{"type":"json_object"}}

def request(provider,model,path,env,*,post=None):
    if (provider,model) not in MODELS:
        raise ValueError("model not allowlisted")
    if not configured(provider,env):
        raise AuditError("free_account_not_confirmed_or_key_missing")
    import requests
    send=post or requests.post
    if provider=="gemini":
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers={"x-goog-api-key":env[KEYS[provider]]}
        payload=native_payload(path)
    else:
        url="https://api.groq.com/openai/v1/chat/completions"
        headers={"Authorization":"Bearer "+env[KEYS[provider]]}
        payload=frame_payload(path,model)
    try:
        response=send(url,headers=headers,json=payload,timeout=(10,120))
    except (requests.RequestException,OSError):
        raise AuditError("network_error") from None
    if response.status_code!=200:
        raise AuditError("HTTP_"+str(response.status_code))
    try:
        data=response.json()
        if provider=="gemini":
            choice=data["candidates"][0]
            if choice.get("finishReason")!="STOP":
                raise ValueError("unfinished")
            raw="".join(p["text"] for p in choice["content"]["parts"]
                        if not p.get("thought") and isinstance(p.get("text"),str))
            actual=data.get("modelVersion")
        else:
            choice=data["choices"][0]
            if choice.get("finish_reason")!="stop":
                raise ValueError("unfinished")
            raw=choice["message"]["content"]
            actual=data.get("model")
        if not isinstance(raw,str) or not raw.strip():
            raise ValueError("empty")
        if actual and not (actual==model or actual.startswith(model+"-")):
            raise AuditError("unexpected_model_version")
        return raw,actual
    except (KeyError,IndexError,TypeError,ValueError):
        raise AuditError("invalid_or_unfinished_response") from None

def main():
    root=Path("cloud-video-audit")
    root.mkdir(exist_ok=True)
    rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        paths=prepare(Path(tmp))
        for provider,model in MODELS:
            for case,path in paths.items():
                row={"provider":provider,"model":model,"case":case,
                     "transport":"native_video" if provider=="gemini" else "ordered_sampled_frames"}
                t=time.monotonic()
                if not configured(provider,os.environ):
                    row["status"]="not_configured"
                else:
                    try:
                        raw,actual=request(provider,model,path,os.environ)
                        row.update(status="evaluated",actual_model=actual,**score(raw,case))
                    except (AuditError,ValueError) as exc:
                        row.update(status="unavailable" if isinstance(exc,AuditError) else "invalid_verdict",
                                   detail=str(exc)[:100] if isinstance(exc,AuditError) else "invalid JSON or verdict")
                    except Exception as exc:
                        row.update(status="error",error_type=type(exc).__name__)
                row["seconds"]=round(time.monotonic()-t,2)
                rows.append(row)
                print("CLOUD VIDEO CASE",json.dumps(row),flush=True)
                (root/"results.json").write_text(json.dumps(rows,indent=2))
    summary=[]
    for provider,model in MODELS:
        subset=[r for r in rows if r["model"]==model]
        tested=sum(r["status"]=="evaluated" for r in subset)*3
        correct=sum(r.get("correct",0) for r in subset)
        summary.append({"model":model,"planned":6,"tested":tested,"correct":correct,
                        "false_positives":sum(r.get("false_positive",0) for r in subset),
                        "pass":tested==correct==6})
    (root/"summary.json").write_text(json.dumps(summary,indent=2))
    print("CLOUD VIDEO SUMMARY",json.dumps(summary),flush=True)
    return 0 if any(r["pass"] for r in summary) else 1

if __name__=="__main__":
    raise SystemExit(main())
