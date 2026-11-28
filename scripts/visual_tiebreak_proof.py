"""Compare the existing two-model gate with a bounded Qwen video tiebreaker.
No production changes. Previously observed clips and fresh catalog clips are
reported separately. Catalog labels are provisional pending manual review.
"""
import json
import subprocess
import tempfile
import time
from pathlib import Path

from media_validation import SceneMatcher, VideoDownloader, _frame
from visual_ensemble_proof import CASES, source, decision
from event_theme_review import motion_pair

HOLDOUT=(
    ("river","freenaturestock_video_catalog.json","autumn-leaves-in-river-water",
     "Autumn leaves floating in river water.","A dry forest floor covered with autumn leaves.","A campfire burning."),
    ("sky","freenaturestock_video_catalog.json","clouds-sun-time-lapse",
     "Clouds and sunlight in the sky.","An entirely cloudless sky.","Fish swimming underwater."),
    ("forest","freenaturestock_video_catalog.json","tall-pine-tree-forest",
     "Tall pine trees in a forest.","A treeless grassy field.","A geyser emitting steam."),
    ("volcano","usgs_public_domain_video_catalog.json","usgs-kilauea-active-ocean-entry-20180521",
     "Volcanic lava at the ocean coast.","An ordinary rocky coast with no volcanic activity.","People riding bicycles."),
    ("debris","usgs_public_domain_video_catalog.json","las-lomas-debris-flow",
     "A muddy debris flow moving through a channel.","A dry channel without flowing debris.","Clouds moving in the sky."),
)
# Every candidate is tested in the same way, regardless of its expected label.
# The tiebreaker has access only to pixels and the competing visual descriptions.
def resolve(base,idx,verdicts=None):
    result=dict(base)
    result["baseline_accepted"]=bool(base["accepted"])
    result["tiebreak"]="not_needed"
    if base["require_motion"] and not base["motion"]:
        result["accepted"]=False
        result["tiebreak"]="motion_veto"
    elif base["clip"] != base["siglip"]:
        result["accepted"]=False
        result["tiebreak"]="abstain"
        if verdicts is not None:
            result["qwen_verdicts"]=list(verdicts)
            # Require affirmative target and explicit rejection of both alternatives.
            # Unknown, invalid, or conflicting responses cannot rescue a candidate.
            if len(verdicts)==3 and verdicts[idx] is True and all(
                    verdicts[j] is False for j in range(3) if j!=idx):
                result["accepted"]=True
                result["tiebreak"]="corroborated"
            else:
                result["tiebreak"]="not_corroborated"
    return result

def adjudicate(bases,ask):
    needs=any(b["clip"]!=b["siglip"] and not (b["require_motion"] and not b["motion"]) for _,_,_,b in bases)
    verdicts=None
    error=None
    if needs:
        try:
            verdicts=ask()
        except Exception as exc:
            error=type(exc).__name__
    result={}
    for label,idx,expected,b in bases:
        row=resolve(b,idx,verdicts)
        row.update(expected=expected,baseline_pass=b["accepted"]==expected,**{"pass":row["accepted"]==expected})
        if error and row["tiebreak"]=="abstain":
            row["tiebreak_error"]=error
        result[label]=row
    return result

def preview(path,target):
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
        "-ss","1","-i",str(path),"-t","2.5","-vf","fps=2,scale=448:-2","-an",
        "-c:v","libx264","-pix_fmt","yuv420p",str(target)],check=True,timeout=60)
    if not target.is_file() or not target.stat().st_size:
        raise ValueError("empty preview")
    return target

def main():
    import torch
    from PIL import Image,ImageDraw
    from siglip_review import score
    from temporal_vision_pilot import local_engine,infer,parse_short_answer,MODELS
    torch.set_num_threads(2)
    out=Path("visual-tiebreak-proof")
    out.mkdir(exist_ok=True)
    matcher=SceneMatcher()
    engine=None
    results={}
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        downloader=VideoDownloader(root/"cache",max_bytes=180*1024*1024,max_cache_bytes=3*1024**3,total_timeout=90)
        for split,cases in (("regression",CASES),("holdout",HOLDOUT)):
            for case in cases:
                name=case[0]
                start=time.monotonic()
                try:
                    path,meta=source(case,root,downloader)
                    queries=list(case[3:])
                    times=(1.,2.,3.)
                    frames=[_frame(path,t,448,preserve_aspect=True) for t in times]
                    adjacent=[_frame(path,t+.24,448,preserve_aspect=True) for t in times]
                    moving=sum(motion_pair(a,b)["localized_change_observed"] for a,b in zip(frames,adjacent))>=2
                    rows=matcher._similarities(frames,queries)
                    other=score(frames,queries)
                    still=[frames[0]]*3
                    still_rows=matcher._similarities(still,queries)
                    still_other=score(still,queries)
                    frozen_motion=any(motion_pair(a,a)["localized_change_observed"] for a in frames)
                    bases=[
                        ("correct_subject",0,True,decision(rows,other,0,moving)),
                        ("same_context_wrong_subject_or_action",1,False,decision(rows,other,1,moving)),
                        ("unrelated_subject",2,False,decision(rows,other,2,moving)),
                        ("frozen_motion_required",0,False,decision(still_rows,still_other,0,frozen_motion,True)),
                    ]
                    raw_answers=[]
                    def ask():
                        nonlocal engine
                        if engine is None:
                            engine=local_engine("qwen2b")
                        clip=preview(path,root/(name+".mp4"))
                        verdicts=[]
                        for q in queries:
                            answer=infer(engine,clip,"Is this description visibly true in the video? "+q)
                            raw_answers.append(answer[:500])
                            try:
                                verdicts.append(parse_short_answer(answer))
                            except ValueError:
                                verdicts.append(None)
                        return verdicts
                    tests=adjudicate(bases,ask)
                    # Keep actual sampled frames for manual review, not web thumbnails.
                    sheet=Image.new("RGB",(448,3*300),"white")
                    draw=ImageDraw.Draw(sheet)
                    for i,im in enumerate(frames):
                        thumb=im.copy()
                        thumb.thumbnail((448,270))
                        sheet.paste(thumb,((448-thumb.width)//2,i*300+20))
                        draw.text((8,i*300+4),f"{name}: {times[i]} sec",fill="black")
                    sheet.save(out/(name+".jpg"),quality=88)
                    result={"state":"evaluated","source":meta,"tests":tests,"queries":queries,
                            "qwen_raw_answers":raw_answers,"clip_scores":rows,"siglip_scores":other,
                            "sample_times":times}
                except Exception as exc:
                    result={"state":"unavailable","error_type":type(exc).__name__,"error":str(exc)[:300]}
                result.update(split=split,seconds=round(time.monotonic()-start,2))
                results[name]=result
                print("TIEBREAK CATEGORY",name,json.dumps(result),flush=True)
    summary={}
    for split in ("regression","holdout"):
        group=[r for r in results.values() if r["split"]==split and r["state"]=="evaluated"]
        tests=[v for r in group for v in r["tests"].values()]
        summary[split]={"planned":20,"evaluated":len(tests),
            "baseline_passed":sum(t["baseline_pass"] for t in tests),
            "passed":sum(t["pass"] for t in tests),
            "false_accepts":sum(t["accepted"] and not t["expected"] for t in tests),
            "false_rejects":sum(not t["accepted"] and t["expected"] for t in tests),
            "rescued_correct":sum(t["accepted"] and t["expected"] and not t["baseline_accepted"] for t in tests),
            "disagreement_abstentions":sum(t["tiebreak"] in ("abstain","not_corroborated") for t in tests)}
    report={"model":MODELS["qwen2b"][0],"categories":results,"summary":summary,
            "scope":"10 catalog-labeled clips, 40 decisions. Holdout clips distinct from regression. Not independent 40 scenes or production approval."}
    (out/"report.json").write_text(json.dumps(report,indent=2))
    print("TIEBREAK SUMMARY",json.dumps(summary),flush=True)
    return 0 if all(s["evaluated"]==20 and s["passed"]>=19 and s["false_accepts"]==0 for s in summary.values()) else 1
if __name__=="__main__":
    raise SystemExit(main())
