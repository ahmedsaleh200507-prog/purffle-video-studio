"""Opt-in sparse-metadata route. Never waive provenance, quality or existing pixel gates.
Only the runtime may accept a candidate after verify_pixels on its final crop.
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

def enabled():
    return os.getenv("PURFFLE_PIXEL_FIRST")=="1"

def metadata_rank(matcher,spec,text):
    from media_validation import ValidationError
    try:
        return matcher.validate_metadata(spec,text),"validated"
    except ValidationError as exc:
        if not str(exc).startswith(("Scene metadata lacks object/action grounding",
                                    "Scene metadata does not describe the requested action")):
            raise
        score=float(matcher.metadata_score(spec,text))
        if not math.isfinite(score):
            raise ValueError("invalid metadata ranking")
        return score,"deferred"

def action_rank(contract,text):
    """Missing tags are not contradiction; explicit negatives remain hard stops."""
    text=str(text).casefold().replace("-"," ").replace("_"," ")
    if re.search(r"\b(?:animation|animated|cartoon|illustration|simulation|cgi|dead|stranded|beached)\b",text):
        return "reject"
    for child in contract.get("sentence_contracts",[]):
        if action_rank(child,text)=="reject":
            return "reject"
    if contract.get("family")=="quiet_volcanic_context" and re.search(r"\b(?:erupt\w*|lava|ash plume|fountain|explosion)\b",text):
        return "reject"
    clues=list(contract.get("metadata_keywords",[]))
    clues.extend(w for group in contract.get("required_metadata_groups",[]) for w in group)
    if clues and re.search(r"\b(?:no|without|lacking|absence of|not showing|never)\s+(?:\w+\s+){0,2}(?:"+"|".join(re.escape(w.casefold()) for w in clues)+r")\b",text):
        return "reject"
    return "pixel_review_required"

def prompts(contract):
    pairs=[(contract["positive"],contract["negative"])]
    for child in contract.get("sentence_contracts",[]):
        pairs.extend(prompts(child))
    return list(dict.fromkeys(pairs))

def corroborates(rows):
    return len(rows)==3 and all(len(r)==3 and all(math.isfinite(float(v)) for v in r) for r in rows) and sum(r[0]>max(r[1:]) for r in rows)>=2

def confirmed(answers):
    return answers==[True,False,False]

def verify_pixels(path,need,focus,contract,matcher,*,deadline,ask=None,secondary=None):
    """Review the exact final portrait interval. Fail closed on missing evidence.
    This adds corroboration to existing full CLIP/event checks, not a replacement.
    """
    from visual_director import _frame_at
    from siglip_review import score
    if not math.isfinite(need) or need<1 or not 0<=focus<=1:
        raise ValueError("invalid review interval")
    pairs=prompts(contract)
    if len(pairs)>3:
        return {"verified":False,"reason":"too_many_distinct_contracts"}
    if deadline-time.monotonic()<20:
        return {"verified":False,"reason":"review_budget_exhausted"}
    times=[need*f for f in (.12,.5,.82)]
    evidence=[]
    frames=[_frame_at(path,t,focus) for t in times]
    for pos,neg in pairs:
        queries=[pos,neg,"An unrelated empty scene or a drawing without the requested visible subject."]
        a=matcher._similarities(frames,queries)
        b=(secondary or score)(frames,queries)
        row={"queries":queries,"clip":a,"siglip":b}
        evidence.append(row)
        if not corroborates(a) or not corroborates(b):
            return {"verified":False,"reason":"independent_visual_disagreement","evidence":evidence}
    if ask is not None:
        answers=ask([r["queries"] for r in evidence])
    else:
        # Isolate CPU model load and inference under the remaining scene deadline.
        # The native MP4 contains only the used crop, never the stock description.
        with tempfile.TemporaryDirectory() as tmp:
            preview=Path(tmp)/"preview.mp4"
            remaining=deadline-time.monotonic()
            if remaining<20:
                return {"verified":False,"reason":"review_budget_exhausted","evidence":evidence}
            vf=(f"scale=252:448:force_original_aspect_ratio=increase,crop=252:448:"
                f"x='max(0,min(iw-ow,iw*{focus:.5f}-ow/2))':y='(ih-oh)/2',setsar=1,fps=2")
            subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-i",str(path),
                 "-t",str(need),"-vf",vf,"-an","-c:v","libx264","-pix_fmt","yuv420p",str(preview)],
                 check=True,timeout=min(15,remaining-5))
            remaining=deadline-time.monotonic()
            if remaining<15:
                return {"verified":False,"reason":"review_budget_exhausted","evidence":evidence}
            p=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(preview),json.dumps([r["queries"] for r in evidence])],
                capture_output=True,text=True,check=False,timeout=min(105,remaining))
            if p.returncode:
                # Report only diagnostic exception classes, never arbitrary child output.
                classes=re.findall(r'(?m)^([A-Za-z_][\w.]*(?:Error|Exception)):',p.stderr)
                return {'verified':False,'reason':'qwen_child_failed','returncode':p.returncode,
                        'exception_types':classes[-5:],'evidence':evidence}
            answers=json.loads(p.stdout.splitlines()[-1])
    if len(answers)!=len(evidence):
        return {"verified":False,"reason":"invalid_qwen_evidence","evidence":evidence}
    for row,verdict in zip(evidence,answers):
        row["qwen"]=verdict
    ok=all(confirmed(a) for a in answers)
    return {"verified":ok,"reason":"corroborated" if ok else "qwen_disagreement_or_uncertainty",
            "interval":[0,need],"sample_times":times,"evidence":evidence,
            "scope":"actual selected portrait interval; not identity, geography or causality proof"}

if __name__=="__main__":
    import torch
    from temporal_vision_pilot import local_engine,infer,parse_short_answer
    torch.set_num_threads(2)
    engine=local_engine("qwen2b")
    result=[]
    for queries in json.loads(sys.argv[2]):
        row=[]
        for q in queries:
            try:
                row.append(parse_short_answer(infer(engine,Path(sys.argv[1]),"Is this description visibly true in the video? "+q)))
            except ValueError:
                row.append(None)
        result.append(row)
    print(json.dumps(result),flush=True)
