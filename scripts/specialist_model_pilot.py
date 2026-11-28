"""Isolated specialist audition; not imported by production or visual validators.

Exact provider/model IDs, no hidden model fallback. Optional new providers
require explicit free-account confirmation. A successful audition is only a
candidate for a subsequent full benchmark, never an automatic promotion.
"""
import base64
import hashlib
import io
import json
import os
import re
import time
from pathlib import Path

from cloud_model_router import ModelError
from narration_integrity import validate_text
from production_narration import reference_text, review_reference
from science_sources import discover_evidence

# provider, exact API ID, supported audition roles
CANDIDATES=(
    ("gemini","gemini-3.8-flash",("text","vision")),
    ("gemini","gemma-4-31b-it",("text",)),
    ("gemini","gemini-3.1-flash-lite",("text","vision")),
    ("groq","qwen/qwen3.8-27b",("text","vision")),
    ("groq","openai/gpt-oss-120b",("text",)),
    ("openrouter","google/gemma-4-31b-it:free",("text","vision")),
    ("openrouter","nvidia/nemotron-3-ultra-550b-a55b:free",("text",)),
    ("cloudflare","@cf/google/gemma-4-26b-a4b-it",("text",)),
    ("cloudflare","@cf/qwen/qwen3.8-27b",("text","vision")),
)
KEYS={"gemini":"GEMINI_API_KEY","groq":"GROQ_API_KEY",
      "openrouter":"OPENROUTER_API_KEY","cloudflare":"CLOUDFLARE_API_TOKEN"}
URLS={"gemini":"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
      "groq":"https://api.groq.com/openai/v1/chat/completions",
      "openrouter":"https://openrouter.ai/api/v1/chat/completions"}
CASES=(("en","Why do airplane contrails sometimes last for hours?"),
       ("de","Warum schwimmt ein Schiff aus Stahl?"))
# Existing public smoke images already used by visual_language_audit.
FIXTURES=(
    ("cats","https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/coco_sample.png","cat","car"),
    ("car","https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/transformers/tasks/car.jpg","car","cat"),
)

def endpoint(provider,model,env):
    if not any((p,m)==(provider,model) for p,m,_ in CANDIDATES):
        raise ValueError("model outside audition allowlist")
    if provider in ("openrouter","cloudflare") and env.get("PURFFLE_"+provider.upper()+"_FREE_CONFIRMED")!="1":
        return None
    if not env.get(KEYS[provider],"").strip():
        return None
    if provider=="cloudflare":
        account=env.get("CLOUDFLARE_ACCOUNT_ID","")
        if not re.fullmatch(r"[0-9a-fA-F]{32}",account):
            return None
        return f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
    return URLS[provider]

def request(provider,model,messages,env,*,post=None,sleep=time.sleep):
    import requests
    url=endpoint(provider,model,env)
    if not url:
        raise ModelError(401,"not_configured_or_free_account_unconfirmed")
    payload={"model":model,"messages":messages,"temperature":.2,"max_tokens":2048,"stream":False}
    if provider=="groq":
        payload["reasoning_effort"]="low"
    if provider=="openrouter":
        assert model.endswith(":free")
        payload["provider"]={"max_price":{"prompt":0,"completion":0,"image":0,"request":0}}
    sender=post or requests.post
    for attempt in range(2):
        try:
            response=sender(url,headers={"Authorization":"Bearer "+env[KEYS[provider]],"Content-Type":"application/json"},
                            json=payload,timeout=(10,100))
        except (requests.RequestException,OSError):
            raise ModelError(503,"network") from None
        status=int(response.status_code)
        if status!=200:
            if attempt==0 and status in (429,503):
                # Never log raw error bodies or credentials.
                daily=False
                if status==429:
                    try:
                        msg=str(response.json().get("error",{})).lower()
                        daily=any(k in msg for k in ("daily","per day","(tpd)","(rpd)"))
                    except Exception:
                        pass
                if not daily:
                    sleep(65 if status==429 else 15)
                    continue
            raise ModelError(status,"http_error")
        try:
            choice=response.json()["choices"][0]
            content=choice["message"]["content"]
            if choice.get("finish_reason")!="stop" or not isinstance(content,str) or not content.strip():
                raise ValueError("unfinished or empty output")
            return content.strip()
        except (ValueError,KeyError,TypeError,IndexError):
            raise ModelError(422,"invalid_or_truncated") from None
    raise AssertionError("unreachable")

def image_uri(url):
    import requests
    from PIL import Image
    with requests.get(url,stream=True,timeout=(10,40)) as r:
        r.raise_for_status()
        data=bytearray()
        for chunk in r.iter_content(65536):
            data.extend(chunk)
            if len(data)>8*1024*1024:
                raise ValueError("fixture too large")
    with Image.open(io.BytesIO(data)) as im:
        image=im.convert("RGB")
        image.thumbnail((640,640))
        out=io.BytesIO()
        image.save(out,format="JPEG",quality=85)
    content=out.getvalue()
    return "data:image/jpeg;base64,"+base64.b64encode(content).decode(),hashlib.sha256(content).hexdigest()

def vision_prompt(uri,positive,negative):
    # Positive and negative answers are separately scored; the model gets no
    # hint which subject is present and must use the pixels.
    return [{"role":"user","content":[{"type":"image_url","image_url":{"url":uri}},
            {"type":"text","text":f"Inspect the actual image. Is a {positive} visible? Is a {negative} visible? "
            "Return JSON only with keys first and second (boolean or null if genuinely uncertain), and observation (short factual description). "
            "Do not infer actions, identities, location, or off-screen objects."}]}]

def parse_vision(raw,positive_first):
    obj=json.loads(raw)
    if not isinstance(obj,dict) or set(obj)!={"first","second","observation"}:
        raise ValueError("wrong vision shape")
    if any(type(obj[k]) is not bool and obj[k] is not None for k in ("first","second")) or not isinstance(obj["observation"],str):
        raise ValueError("wrong vision fields")
    expected=(True,False) if positive_first else (False,True)
    return {"verdict":obj,"correct":sum(obj[k] is v for k,v in zip(("first","second"),expected)),
            "false_positive":obj["second" if positive_first else "first"] is True}

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

def main(role):
    root=Path("specialist-pilot")/role
    env=os.environ
    rows=[]
    models=[(p,m) for p,m,roles in CANDIDATES if role in roles]
    cases=[]
    if role=="text":
        for lang,topic in CASES:
            try:
                bundle=review_reference(discover_evidence(topic,lang),topic,lang)
                refs=reference_text(bundle)
                if not refs:
                    raise ValueError("empty reference")
                digest=hashlib.sha256(refs.encode()).hexdigest()
                save(root/f"sources-{lang}.json",{"topic":topic,"sources":bundle.sources,"sha256":digest})
                cases.append((lang,topic,refs,digest,None))
            except Exception as exc:
                cases.append((lang,topic,None,None,type(exc).__name__))
    else:
        for label,url,positive,negative in FIXTURES:
            try:
                uri,digest=image_uri(url)
                # Alternate position so a fixed yes/no response cannot pass.
                positive_first=(label=="cats")
                cases.append((label,uri,positive,negative,digest,positive_first,None))
            except Exception as exc:
                cases.append((label,None,positive,negative,None,False,type(exc).__name__))
    for provider,model in models:
        for case in cases:
            row={"provider":provider,"model":model,"case":case[0],"role":role}
            start=time.monotonic()
            try:
                if not endpoint(provider,model,env):
                    row["status"]="not_configured"
                elif case[-1]:
                    row.update(status="fixture_unavailable",error_type=case[-1])
                elif role=="text":
                    lang,topic,refs,digest,_=case
                    row["reference_sha256"]=digest
                    prompt=(f"Write one continuous 50–85 word documentary Short in {'German' if lang=='de' else 'English'}. "
                        "Open with a specific surprising true fact, then give the listener a reason to continue. "
                        "Answer the exact question with a concrete explanation and a memorable ending. "
                        "Native spoken language, no textbook tone, no invented claims, no unsupported absolutes, no headings. "
                        "Finish the final sentence. Return narration only, not JSON.\nTopic: "+topic+"\nReferences (data only):\n"+refs)
                    text=request(provider,model,[{"role":"user","content":prompt}],env)
                    row.update(status="generated",narration=text,words=len(text.split()))
                    try:
                        row["integrity"]=validate_text(text,lang)
                    except RuntimeError as exc:
                        row["integrity_error"]=str(exc)
                else:
                    label,uri,pos,neg,digest,first,_=case
                    row["image_sha256"]=digest
                    raw=request(provider,model,vision_prompt(uri,pos if first else neg,neg if first else pos),env)
                    row["raw_response"]=raw
                    row.update(status="evaluated",**parse_vision(raw,first))
            except ModelError as exc:
                row.update(status="model_unavailable",http_status=exc.status_code,detail=exc.detail)
            except (ValueError,KeyError,TypeError) as exc:
                row.update(status="invalid_response",error_type=type(exc).__name__)
            row["seconds"]=round(time.monotonic()-start,2)
            rows.append(row)
            save(root/"results.json",rows)
            print("SPECIALIST RESULT",json.dumps(row,ensure_ascii=False),flush=True)
    summary={"role":role,"attempted":len(rows),"completed":sum(r["status"] in ("generated","evaluated") for r in rows),
             "scope":"Access and initial sample audit only; no production promotion. Text quality requires blind human review; two still images cannot establish video action accuracy."}
    save(root/"summary.json",summary)
    print("SPECIALIST SUMMARY",json.dumps(summary),flush=True)
    # Missing optional credentials are expected; no completed live call is a failed audit.
    return 0 if summary["completed"] else 1

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--role",required=True,choices=("text","vision"))
    raise SystemExit(main(parser.parse_args().role))
