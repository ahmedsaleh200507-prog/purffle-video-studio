"""Real-video contrast audit. Not a production acceptance gate.

All five engines inspect the same decoded pedestrian footage. Compare a known
present category against an unrelated category. No identity/action claims.
"""
import argparse
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path

import requests
from media_validation import _frame
from object_framing_audit import VIDEO_URL, VIDEO_SHA

def fixture(path):
    size=0
    with requests.get(VIDEO_URL, timeout=(15,45), stream=True) as r:
        r.raise_for_status()
        with path.open("wb") as fp:
            for chunk in r.iter_content(65536):
                size+=len(chunk)
                if size>16*1024*1024:
                    raise ValueError("Fixture exceeds download bound")
                fp.write(chunk)
    digest=hashlib.sha1()
    digest.update(f"blob {size}".encode()+bytes([0]))
    with path.open("rb") as fp:
        for chunk in iter(lambda:fp.read(65536),b""):
            digest.update(chunk)
    if digest.hexdigest()!=VIDEO_SHA:
        raise ValueError("Unexpected fixture bytes")

def evaluate(key, frames):
    positive="A documentary video frame of people outdoors on a walkway."
    negative="A documentary video frame of whales underwater in the ocean."
    if key in ("clip","siglip"):
        if key=="clip":
            from media_validation import SceneMatcher
            scores=SceneMatcher()._similarities(frames,[positive,negative])
        else:
            from siglip_review import score
            scores=score(frames,[positive,negative])
        passed=[r[0]>r[1] for r in scores]
        return {"scores":scores,"positive_wins":passed,"pass":sum(passed)>=2,
                "scope":"relative text-image ranking; no calibrated accuracy"}
    if key=="dino":
        from object_framing import detect
        rows=[{"person":detect(frame,"person"),"whale":detect(frame,"whale")} for frame in frames]
        passed=[bool(r["person"]) and not r["whale"] for r in rows]
        return {"detections":rows,"positive_wins":passed,"pass":sum(passed)>=2,
                "scope":"category localization; no identity or action proof"}
    if key=="dino_verified":
        from object_framing import detect
        from object_region_review import corroborate
        rows=[]
        for frame in frames:
            row={}
            for subject in ("person","whale"):
                raw=detect(frame,subject)
                row[subject]={"raw":raw,**corroborate(frame,subject,raw)}
            rows.append(row)
        passed=[bool(r["person"]["accepted"]) and not r["whale"]["accepted"] for r in rows]
        return {"regions":rows,"positive_wins":passed,"pass":sum(passed)>=2,
                "scope":"independent crop corroboration; raw detector errors retained; no identity/action proof"}
    from visual_language_audit import load_engine, caption
    processor, model=load_engine(key)
    rows=[]
    for frame in frames:
        answer=caption(key,processor,model,frame)
        present=bool(re.search(r"\b(?:people|person|pedestrians?|men|man|women|woman|humans?|individuals?|walkers?|boys?|girls?|persons?)\b",answer,re.I))
        absent=not bool(re.search(r"\bwhales?\b",answer,re.I))
        rows.append({"caption":answer,"person_word":present,"no_whale_word":absent,"pass":present and absent})
    return {"captions":rows,"pass":sum(r["pass"] for r in rows)>=2,
            "scope":"caption category smoke; no motion understanding"}

def main():
    import torch
    torch.set_num_threads(2)
    p=argparse.ArgumentParser()
    p.add_argument("--model",choices=["clip","siglip","dino","florence","qwen","dino_verified"],required=True)
    key=p.parse_args().model
    out=Path("video-contrast-audit")
    out.mkdir(exist_ok=True)
    report={"model":key,"fixture":VIDEO_URL,"sample_times":[1.,4.,7.],
            "pass":False,"scope":"one real test clip, not representative footage evaluation"}
    try:
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"sample.avi"
            fixture(path)
            frames=[_frame(path,t,640,preserve_aspect=True) for t in report["sample_times"]]
            start=time.monotonic()
            report.update(evaluate(key,frames))
            report["seconds"]=round(time.monotonic()-start,2)
        if not report["pass"]:
            raise RuntimeError("Real video contrast check did not pass")
    except Exception as exc:
        report.update(error_type=type(exc).__name__,error=str(exc))
        raise
    finally:
        (out/(key+".json")).write_text(json.dumps(report,indent=2),encoding="utf8")
        print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
