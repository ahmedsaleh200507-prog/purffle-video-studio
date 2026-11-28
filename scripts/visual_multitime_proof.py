"""Experimental segment selector, no production imports or inference APIs.

Three bounded windows per source. Labels are catalog-derived hypotheses, not
human annotation of each interval. Export evidence and exact chosen intervals
for review. Never replace unknown evidence with a positive.
"""
import argparse
import json
import math
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from media_validation import SceneMatcher, VideoDownloader, _frame
from visual_ensemble_proof import CASES, source, decision
from visual_tiebreak_proof import HOLDOUT
from event_theme_review import motion_pair

NATURE="freenaturestock_video_catalog.json"
USGS="usgs_public_domain_video_catalog.json"
FRESH=(
    ("mist",NATURE,"rolling-mist-clouds","Mist or clouds covering a landscape.","An entirely clear landscape with no mist or clouds.","People riding bicycles."),
    ("stars",NATURE,"starry-night-rising","Stars visible in a dark night sky.","A bright daytime sky without visible stars.","A campfire burning."),
    ("shore",NATURE,"rocky-river-shoreline","A rocky shoreline beside river water.","A dry rocky area without visible water.","A forest fire."),
    ("maple",NATURE,"golden-maple-tree-breeze","Golden autumn maple foliage on a tree.","A leafless tree with bare branches.","Fish swimming underwater."),
    ("waterfall",NATURE,"leaves-dancing-before-a-waterfall","Foliage in front of a waterfall.","A dry rock face without any falling water.","People riding bicycles."),
    ("ripples",NATURE,"golden-water-ripples-at-sunset","Golden light reflected on rippling water.","A dry sandy surface without water.","A campfire burning."),
    ("milky",NATURE,"milky-way-through-clouds","Stars and clouds visible in a night sky.","A bright cloudless daytime sky.","A geyser erupting."),
    ("lava_laze",USGS,"usgs-kilauea-ocean-entry-laze-20180609","Volcanic activity with steam at the ocean coast.","An ordinary coastline without visible volcanic activity or steam.","People riding bicycles."),
    ("lava_kapoho",USGS,"usgs-kilauea-kapoho-bay-20180612","Volcanic lava or volcanic steam near ocean water.","A calm coastline with no visible volcanic activity.","A campfire in a forest."),
    ("postfire",USGS,"postfire-debris-flow-2024-elk-fire-burn-area","Muddy debris or water flowing through a channel.","A dry channel without visible flowing water or debris.","Stars in the night sky."),
)
GROUPS={"regression":CASES+HOLDOUT,"fresh":FRESH}
# Fixed conservative pilot thresholds, not calibrated probabilities.
CLIP_ABSOLUTE=.24
CLIP_MARGIN=.02
SIGLIP_ABSOLUTE=-4.
SIGLIP_MARGIN=1.

def windows(duration):
    if not math.isfinite(duration) or duration<3:
        raise ValueError("video too short for bounded windows")
    length=min(2.5,duration)
    return [(max(0.,min(duration-length,duration*f-length/2)),length) for f in (.12,.50,.88)]

def duration_of(path):
    raw=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1",str(path)],timeout=30,text=True)
    return float(raw.strip())

def stats(rows,idx,absolute,margin):
    if len(rows)!=3 or any(len(r)!=3 or not all(math.isfinite(float(v)) for v in r) for r in rows):
        raise ValueError("invalid similarity matrix")
    m=[float(r[idx])-max(float(v) for j,v in enumerate(r) if j!=idx) for r in rows]
    values=[float(r[idx]) for r in rows]
    return {"wins":sum(v>0 for v in m),"median_score":statistics.median(values),
            "median_margin":statistics.median(m),
            "strong":sum(v>0 for v in m)>=2 and statistics.median(values)>=absolute and statistics.median(m)>=margin}

def evaluate_window(primary,secondary,moving,ask):
    """Ask Qwen on all non-strong candidates having at least one model vote.
    Even strong agreement is checked by Qwen here to expose shared mistakes.
    Preserve strong vs weak distinction in report; no forced majority guessing.
    """
    rows=[]
    for idx in range(3):
        a=stats(primary,idx,CLIP_ABSOLUTE,CLIP_MARGIN)
        b=stats(secondary,idx,SIGLIP_ABSOLUTE,SIGLIP_MARGIN)
        rows.append({"clip":a,"siglip":b,"strong_agreement":a["strong"] and b["strong"],
                     "candidate":a["wins"]>=2 or b["wins"]>=2})
    verdicts=None
    error=None
    if any(r["candidate"] for r in rows):
        try:
            verdicts=ask()
        except Exception as exc:
            error=type(exc).__name__
    for idx,row in enumerate(rows):
        row["accepted"]=bool(row["candidate"] and verdicts is not None and len(verdicts)==3 and
                             verdicts[idx] is True and all(verdicts[j] is False for j in range(3) if j!=idx))
        row["review"]="corroborated" if row["accepted"] else ("abstain" if row["candidate"] else "no_similarity_vote")
    return {"candidates":rows,"motion":moving,"qwen_verdicts":verdicts,"review_error":error}

def select_window(results,idx,require_motion=False):
    eligible=[r for r in results if r["candidates"][idx]["accepted"] and
              (r["motion"] if require_motion else True)]
    if not eligible:
        return None
    return max(eligible,key=lambda r:(r["candidates"][idx]["strong_agreement"],
                                     r["candidates"][idx]["clip"]["median_margin"],
                                     r["candidates"][idx]["siglip"]["median_margin"]))

def make_preview(path,target,start,length):
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
        "-ss",str(start),"-i",str(path),"-t",str(length),"-vf","fps=2,scale=448:-2","-an",
        "-c:v","libx264","-pix_fmt","yuv420p",str(target)],check=True,timeout=60)
    if not target.is_file() or not target.stat().st_size:
        raise ValueError("empty preview")
    return target

def main(group,shard):
    import torch
    from PIL import Image,ImageDraw
    from siglip_review import score
    from temporal_vision_pilot import local_engine,infer,parse_short_answer
    torch.set_num_threads(2)
    out=Path("visual-multitime-proof")
    out.mkdir(exist_ok=True)
    cases=GROUPS[group][shard*5:(shard+1)*5]
    matcher=SceneMatcher()
    engine=None
    results={}
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        downloader=VideoDownloader(root/"cache",max_bytes=180*1024*1024,max_cache_bytes=2*1024**3,total_timeout=90)
        for case in cases:
            name=case[0]
            started=time.monotonic()
            try:
                path,meta=source(case,root,downloader)
                duration=duration_of(path)
                queries=list(case[3:])
                evidence=[]
                # Measure the former early-only gate independently for diagnosis.
                early=[_frame(path,t,448,preserve_aspect=True) for t in (1.,2.,3.)]
                early_a=matcher._similarities(early,queries)
                early_b=score(early,queries)
                baseline=[decision(early_a,early_b,i,True)["accepted"] for i in range(3)]
                sheet=Image.new("RGB",(448*3,3*300),"white")
                draw=ImageDraw.Draw(sheet)
                for k,(start,length) in enumerate(windows(duration)):
                    times=[start+length*f for f in (.15,.45,.75)]
                    frames=[_frame(path,t,448,preserve_aspect=True) for t in times]
                    adjacent=[_frame(path,min(t+.20,start+length-.01),448,preserve_aspect=True) for t in times]
                    moving=sum(motion_pair(a,b)["localized_change_observed"] for a,b in zip(frames,adjacent))>=2
                    primary=matcher._similarities(frames,queries)
                    secondary=score(frames,queries)
                    raw=[]
                    def ask():
                        nonlocal engine
                        if engine is None:
                            engine=local_engine("qwen2b")
                        clip=make_preview(path,root/"preview.mp4",start,length)
                        verdicts=[]
                        for query in queries:
                            answer=infer(engine,clip,"Is this description visibly true in the video? "+query)
                            raw.append(answer[:500])
                            try:
                                verdicts.append(parse_short_answer(answer))
                            except ValueError:
                                verdicts.append(None)
                        return verdicts
                    row=evaluate_window(primary,secondary,moving,ask)
                    row.update(start=start,length=length,times=times,raw_answers=raw,
                               clip_scores=primary,siglip_scores=secondary)
                    evidence.append(row)
                    for i,frame in enumerate(frames):
                        thumb=frame.copy()
                        thumb.thumbnail((448,270))
                        sheet.paste(thumb,(k*448+(448-thumb.width)//2,i*300+20))
                        draw.text((k*448+8,i*300+4),f"{name}: {times[i]:.2f}s",fill="black")
                sheet.save(out/(name+".jpg"),quality=88)
                tests={}
                for i,label in enumerate(("correct_subject","same_context_wrong_subject_or_action","unrelated_subject")):
                    selected=select_window(evidence,i)
                    expected=i==0
                    tests[label]={"expected":expected,"accepted":selected is not None,
                                  "pass":(selected is not None)==expected,
                                  "selected_interval":None if selected is None else [selected["start"],selected["length"]]}
                # A frozen copy must not pass the very same motion gate, even
                # if the semantic verdict were positive.
                frozen=[]
                for row in evidence:
                    clone=dict(row)
                    frame=_frame(path,row["times"][0],448,preserve_aspect=True)
                    clone["motion"]=motion_pair(frame,frame)["localized_change_observed"]
                    frozen.append(clone)
                accepted=select_window(frozen,0,require_motion=True) is not None
                tests["frozen_motion_required"]={"expected":False,"accepted":accepted,"pass":not accepted}
                result={"state":"evaluated","source":meta,"duration":duration,"queries":queries,
                        "early_only_baseline":baseline,"windows":evidence,"tests":tests,
                        "label_scope":"catalog-level provisional labels; selected intervals need human review"}
            except Exception as exc:
                result={"state":"unavailable","error_type":type(exc).__name__,"error":str(exc)[:300]}
            result["seconds"]=round(time.monotonic()-started,2)
            results[name]=result
            print("MULTITIME CATEGORY",name,json.dumps(result),flush=True)
            (out/"report.json").write_text(json.dumps({"group":group,"shard":shard,"categories":results},indent=2))
    evaluated=[r for r in results.values() if r["state"]=="evaluated"]
    tests=[t for r in evaluated for t in r["tests"].values()]
    summary={"planned":len(cases)*4,"evaluated":len(tests),"passed":sum(t["pass"] for t in tests),
             "false_accepts":sum(t["accepted"] and not t["expected"] for t in tests),
             "false_rejects":sum(not t["accepted"] and t["expected"] for t in tests),
             "review_errors":sum(bool(w["review_error"]) for r in evaluated for w in r["windows"]),
             "sources":len(evaluated),"windows":sum(len(r["windows"]) for r in evaluated)}
    (out/"report.json").write_text(json.dumps({"group":group,"shard":shard,"categories":results,"summary":summary},indent=2))
    print("MULTITIME SUMMARY",group,shard,json.dumps(summary),flush=True)
    return 0 if summary["evaluated"]==summary["planned"] and summary["passed"]>=math.ceil(.98*summary["planned"]) and summary["false_accepts"]==0 and summary["review_errors"]==0 else 1

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--group",choices=GROUPS,required=True)
    p.add_argument("--shard",type=int,choices=(0,1),required=True)
    args=p.parse_args()
    raise SystemExit(main(args.group,args.shard))
