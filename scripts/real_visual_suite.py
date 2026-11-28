"""Bounded real-footage audit; never a production approval or license bypass."""
import argparse
import hashlib
import json
import math
import re
import tempfile
import time
from pathlib import Path

import requests
from media_validation import _frame
from video_contrast_audit import fixture
from object_framing_audit import VIDEO_URL

ROOT=Path(__file__).resolve().parents[1]
def fish_fixture(path):
    source=json.loads((ROOT/"docs/visual-live-test.json").read_text())["results"][0]
    # Resolve the exact previously tested asset, not a fresh search result.
    name=source["source_page"].split("/wiki/File:",1)[1]
    h=hashlib.md5(name.encode()).hexdigest()
    url=f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[:2]}/{requests.utils.quote(name,safe='')}"
    # Respect Retry-After; only the fixture preparation job contacts Wikimedia.
    for attempt in range(3):
        response=requests.get(url,stream=True,timeout=(15,45),
            headers={"User-Agent":"PurffleVideoStudio/2.0 (real visual audit; github.com/ahmedsaleh200507-prog/purffle-video-studio)"})
        if response.status_code not in (429,503):
            break
        retry=response.headers.get("Retry-After","")
        response.close()
        if attempt==2:
            raise RuntimeError("Fixture temporarily rate limited")
        try:
            delay=max(15.,float(retry))
        except ValueError:
            from email.utils import parsedate_to_datetime
            try:
                delay=max(15.,parsedate_to_datetime(retry).timestamp()-time.time())
            except (TypeError,ValueError,OverflowError):
                delay=20.*(attempt+1)
        if not math.isfinite(delay) or delay>90:
            raise RuntimeError("Fixture Retry-After exceeds audit time budget")
        time.sleep(delay)
    digest=hashlib.sha256()
    size=0
    with response:
        response.raise_for_status()
        with path.open("wb") as fp:
            for chunk in response.iter_content(65536):
                size+=len(chunk)
                if size>80*1024*1024:
                    raise ValueError("Fish fixture exceeds limit")
                digest.update(chunk)
                fp.write(chunk)
    if size!=source["download"]["bytes"] or digest.hexdigest()!=source["download"]["sha256"]:
        raise ValueError("Fish fixture bytes do not match recorded sample")
    return source["source_page"]

CASES={
    "people":{"subject":"person","absent":"whale",
        "positive":"People walking outdoors on a paved walkway.",
        "negatives":["An empty paved walkway with no people.","Whales swimming underwater."],
        "present_words":r"\b(?:people|person|pedestrians?|men|man|women|woman|humans?|individuals?|walkers?)\b",
        "absent_words":r"\bwhales?\b","times":[1.,4.,7.]},
    "fish":{"subject":"fish","absent":"person",
        "positive":"Fish swimming underwater in the sea.",
        "negatives":["Empty underwater scenery with no fish.","People walking on a paved street."],
        "present_words":r"\b(?:fish|fishes|fish school|sea bream)\b",
        "absent_words":r"\b(?:people|person|pedestrians?)\b","times":[.2,1.2,2.7]}
}

def evaluate(model,frames,case,caption_engine=None):
    if model in ("clip","siglip"):
        if model=="clip":
            from media_validation import SceneMatcher
            score=SceneMatcher()._similarities
        else:
            from siglip_review import score
        rows=score(frames,[case["positive"],*case["negatives"]])
        if len(rows)!=len(frames) or any(len(r)!=3 or not all(math.isfinite(v) for v in r) for r in rows):
            raise ValueError("Invalid score matrix")
        wins=[r[0]>max(r[1:]) for r in rows]
        return {"pass":sum(wins)>=2,"wins":wins,"scores":rows,
                "scope":"relative positive versus same-context empty background and unrelated category"}
    if model=="dino":
        from object_framing import detect, track_focus, group_focus
        from object_region_review import corroborate
        rows=[]
        for frame in frames:
            entry={}
            for label in ("subject","absent"):
                raw=detect(frame,case[label])
                entry[label]={"raw":raw,**corroborate(frame,case[label],raw)}
            rows.append(entry)
        wins=[bool(r["subject"]["accepted"]) and not r["absent"]["accepted"] for r in rows]
        w,h=frames[0].size
        verified=[r["subject"]["accepted"] for r in rows]
        fraction=min(1.,h*9/(w*16))
        tracking=track_focus(verified,case["times"],fraction)
        group=group_focus(verified,fraction)
        return {"pass":sum(wins)>=2,"wins":wins,"regions":rows,"tracking":tracking,"group_framing":group,
                "scope":"independently corroborated boxes; tracking proposal or abstention, no identity ground truth"}
    from visual_language_audit import caption
    processor,engine=caption_engine
    captions=[caption(model,processor,engine,frame) for frame in frames]
    wins=[bool(re.search(case["present_words"],a,re.I)) and not re.search(case["absent_words"],a,re.I) for a in captions]
    return {"pass":sum(wins)>=2,"wins":wins,"captions":captions,
            "scope":"caption category smoke, not action recognition"}

def motion_audit(path):
    from event_theme_review import motion_pair
    pairs=[(_frame(path,t,320,preserve_aspect=True),_frame(path,t+.24,320,preserve_aspect=True))
           for t in (.2,1.,2.,3.)]
    moving=[motion_pair(a,b) for a,b in pairs]
    frozen=[motion_pair(a,a) for a,b in pairs]
    return {"pass":sum(r["localized_change_observed"] for r in moving)>=2 and not any(r["localized_change_observed"] for r in frozen),
            "moving":moving,"frozen":frozen,"scope":"actual adjacent frames versus frozen controls; not semantic motion"}

def sha256(path):
    digest=hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda:fp.read(65536),b""):
            digest.update(chunk)
    return digest.hexdigest()

def prepare_fixtures(directory):
    directory.mkdir(parents=True,exist_ok=True)
    manifest={}
    for name in CASES:
        path=directory/(name+(".avi" if name=="people" else ".webm"))
        try:
            if name=="people":
                fixture(path)
                source=VIDEO_URL
            else:
                source=fish_fixture(path)
            manifest[name]={"state":"ready","source":source,"sha256":sha256(path)}
        except Exception as exc:
            path.unlink(missing_ok=True)
            manifest[name]={"state":"unavailable","error":str(exc)[:500]}
        print("[FIXTURE]",name,manifest[name],flush=True)
    (directory/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf8")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--model",choices=["clip","siglip","dino","florence","qwen","motion"])
    parser.add_argument("--prepare",action="store_true")
    parser.add_argument("--fixtures",type=Path,required=True)
    args=parser.parse_args()
    if args.prepare:
        prepare_fixtures(args.fixtures)
        return
    if not args.model:
        parser.error("--model is required unless preparing fixtures")
    import torch
    torch.set_num_threads(2)
    out=Path("real-visual-suite")
    out.mkdir(exist_ok=True)
    report={"model":args.model,"cases":{},"pass":False,
            "scope":"two known real clips only; no production acceptance, general accuracy, or exact action labels"}
    engine=None
    try:
        if args.model in ("florence","qwen"):
            from visual_language_audit import load_engine
            engine=load_engine(args.model)
        manifest=json.loads((args.fixtures/"manifest.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            for name,case in CASES.items():
                start=time.monotonic()
                try:
                    path=Path(directory)/(name+(".avi" if name=="people" else ".webm"))
                    entry=manifest.get(name,{})
                    if entry.get("state")!="ready":
                        raise RuntimeError("fixture_unavailable: "+entry.get("error","missing manifest entry"))
                    path=args.fixtures/path.name
                    if not path.is_file() or sha256(path)!=entry.get("sha256"):
                        raise ValueError("Shared fixture integrity mismatch")
                    source=entry["source"]
                    if args.model=="motion":
                        row=motion_audit(path)
                    else:
                        frames=[_frame(path,t,640,preserve_aspect=True) for t in case["times"]]
                        row=evaluate(args.model,frames,case,engine)
                    row["source"]=source
                except Exception as exc:
                    row={"pass":False,"state":"unavailable" if "fixture_" in str(exc) else "error","error_type":type(exc).__name__,"error":str(exc)[:500]}
                row["seconds"]=round(time.monotonic()-start,2)
                report["cases"][name]=row
                print("[REAL VISUAL CASE]",args.model,name,json.dumps(row,ensure_ascii=False),flush=True)
            report["pass"]=all(row["pass"] for row in report["cases"].values()) and len(report["cases"])==len(CASES)
    finally:
        (out/(args.model+".json")).write_text(json.dumps(report,indent=2),encoding="utf8")
    if not report["pass"]:
        raise RuntimeError("Real visual suite has failed or unavailable cases")

if __name__=="__main__":
    main()
