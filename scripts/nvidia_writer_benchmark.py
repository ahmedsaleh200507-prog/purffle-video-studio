"""Internal evaluation only: NVIDIA Build free trial endpoints, never production.
At most 30 writer requests, no paid endpoints, retries, or fallback.
"""
import hashlib
import json
import os
import random
import time
from pathlib import Path

from cloud_model_router import Router, ModelError
from narration_model_benchmark import CASES, evaluate
from specialist_model_pilot import save, validate_narration_output
from openrouter_writer_benchmark import writer_prompt
from science_sources import discover_evidence, Evidence
from production_narration import review_reference, reference_text

WRITERS=("moonshotai/kimi-k3.1-pro","z-ai/glm-5.3-flash","nvidia/nemotron-3-ultra-550b-a55b")
JUDGES=("gemini-3.1-flash-lite","qwen/qwen3.8-27b")
MAX_WRITER_CALLS=30
URL="https://integrate.api.nvidia.com/v1/chat/completions"

def configured(env):
    return env.get("PURFFLE_NVIDIA_FREE_CONFIRMED")=="1" and bool(env.get("NVIDIA_API_KEY","").strip())

def request(model,prompt,env,*,post=None):
    import requests
    if model not in WRITERS:
        raise ValueError("model outside free trial allowlist")
    if not configured(env):
        raise ModelError(401,"free_trial_not_confirmed")
    payload={"model":model,"messages":[{"role":"user","content":prompt}],
             "max_tokens":4096,"stream":False}
    if model.startswith("moonshotai/"):
        payload["reasoning_effort"]="low"
    else:
        payload["temperature"]=.2
    if model.startswith("nvidia/"):
        payload["chat_template_kwargs"]={"enable_thinking":False}
    try:
        response=(post or requests.post)(URL,headers={"Authorization":"Bearer "+env["NVIDIA_API_KEY"],
                   "Accept":"application/json","Content-Type":"application/json"},
                   json=payload,timeout=(10,120),allow_redirects=False)
    except (requests.RequestException,OSError):
        raise ModelError(503,"network") from None
    if response.status_code!=200:
        raise ModelError(response.status_code,"trial_http_error")
    try:
        choice=response.json()["choices"][0]
        content=choice["message"]["content"]
        if choice.get("finish_reason")!="stop" or not isinstance(content,str) or not content.strip():
            raise ValueError("empty or unfinished")
        return content.strip()
    except (ValueError,KeyError,IndexError,TypeError):
        raise ModelError(422,"invalid_or_truncated") from None

def main():
    root=Path("nvidia-writer-benchmark")
    rows=[]
    calls=0
    router=Router()
    blocked={}
    if not configured(os.environ):
        print("NVIDIA TRIAL NOT CONFIGURED",flush=True)
        return 1
    if len(WRITERS)*len(CASES)*2>MAX_WRITER_CALLS:
        raise ValueError("NVIDIA trial call budget exceeded")
    for index,(category,en,de) in enumerate(CASES):
        shared=None
        for source_lang,source_topic in (("en",en),("de",de)):
            try:
                found=review_reference(discover_evidence(source_topic,source_lang),source_topic,source_lang)
                if reference_text(found):
                    shared=found
                    break
            except (RuntimeError,ValueError,KeyError,OSError):
                continue
        for lang,topic in (("en",en),("de",de)):
            case=f"{category}-{lang}"
            path=root/case
            bundle=None
            try:
                if shared is None:
                    raise ValueError("no source passages")
                bundle=Evidence(topic,shared.sources,shared.method)
                refs=reference_text(bundle)
                if not refs:
                    raise ValueError("no source passages")
                digest=hashlib.sha256(refs.encode()).hexdigest()
                save(path/"sources.json",{"topic":topic,"sources":bundle.sources,"reference_text":refs,"sha256":digest})
            except (RuntimeError,ValueError,KeyError,OSError) as exc:
                bundle=None
                print("SOURCE UNAVAILABLE",case,type(exc).__name__,flush=True)
            candidates=[]
            for model in WRITERS:
                row={"case":case,"language":lang,"topic":topic,"provider":"nvidia_trial","model":model}
                start=time.monotonic()
                try:
                    if not configured(os.environ):
                        row["status"]="not_configured"
                    elif model in blocked:
                        row.update(status="previous_permanent_error",http_status=blocked[model])
                    elif bundle is None:
                        row["status"]="source_unavailable"
                    else:
                        row["reference_sha256"]=digest
                        calls+=1
                        text=request(model,writer_prompt(topic,lang,refs),os.environ)
                        row["words"]=len(text.split())
                        try:
                            row["integrity"]=validate_narration_output(text,lang)
                        except (RuntimeError,ValueError) as exc:
                            row.update(status="invalid_narration",integrity_error=str(exc))
                        else:
                            row.update(status="generated",narration=text)
                            candidates.append(row)
                except ModelError as exc:
                    row.update(status="model_unavailable",http_status=exc.status_code,detail=exc.detail)
                    if exc.status_code in (401,402,403):
                        blocked.update({m:exc.status_code for m in WRITERS})
                    elif exc.status_code in (404,410):
                        blocked[model]=exc.status_code
                row["seconds"]=round(time.monotonic()-start,2)
                rows.append(row)
                save(root/"results.json",rows)
                print("NVIDIA CANDIDATE",json.dumps(row,ensure_ascii=False),flush=True)
            order=list(candidates)
            random.Random(index*2+(lang=="de")).shuffle(order)
            save(path/"blind-scripts.json",{f"candidate-{i+1}":r["narration"] for i,r in enumerate(order)})
            save(path/"blind-key.json",{f"candidate-{i+1}":r["model"] for i,r in enumerate(order)})
            judge=evaluate(router,bundle,lang,candidates,index*2+(lang=="de"),judges=JUDGES) if candidates else None
            for row in candidates:
                row["status"]="reviewed" if judge else "review_unavailable"
                print("NVIDIA RESULT",json.dumps(row,ensure_ascii=False),flush=True)
            save(root/"results.json",rows)
    summary=[]
    for model in WRITERS:
        for lang in ("en","de"):
            subset=[r for r in rows if r["model"]==model and r["language"]==lang]
            reviewed=[r for r in subset if r["status"]=="reviewed"]
            accepted=[r for r in reviewed if r["accepted"]]
            summary.append({"model":model,"language":lang,"planned":len(subset),
                "generated":sum("narration" in r for r in subset),"reviewed":len(reviewed),"accepted":len(accepted),
                "mean_reviewed_score":round(sum(r["weighted_score"] for r in reviewed)/len(reviewed),2) if reviewed else None,
                "spoken_flow_100":round(10*sum(r["review"]["scores"]["spoken_flow"] for r in reviewed)/len(reviewed),2) if reviewed else None,
                "ending_100":round(10*sum(r["review"]["scores"]["ending"] for r in reviewed)/len(reviewed),2) if reviewed else None,
                "material_errors":sum(r["review"]["material_error"] for r in reviewed),
                "statuses":{s:sum(r["status"]==s for r in subset) for s in sorted({r["status"] for r in subset})}})
    full_cases=sorted(c for c in {r["case"] for r in rows} if sum(r["case"]==c and r["status"]=="reviewed" for r in rows)==len(WRITERS))
    report={"writers":list(WRITERS),"nvidia_trial_calls":calls,"rows":summary,"fully_matched_cases":full_cases,
            "scope":"Independent model scores are advisory, not human factual verification or retention measurements. Internal trial evaluation only. No automatic production promotion; production licensing not established."}
    save(root/"summary.json",report)
    print("NVIDIA SUMMARY",json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if len(full_cases)==len(CASES)*2 else 1

if __name__=="__main__":
    raise SystemExit(main())
