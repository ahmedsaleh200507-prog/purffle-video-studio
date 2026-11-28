"""Opt-in, offline-model ensemble benchmark; never a production acceptance gate.

Five source categories and four decisions per category, not 20 independent
source videos. Catalog labels are provisional until a human watches the
saved intervals. Unavailable clips are not counted as successful.
"""
import json
import math
import statistics
import tempfile
from pathlib import Path
from media_validation import SceneMatcher, VideoDownloader, _frame
from video_contrast_audit import fixture
from event_theme_review import motion_pair

ROOT=Path(__file__).resolve().parents[1]
# Catalog IDs and literal visual contrast queries. No live discovery/scraping.
CASES=(
    ("people",None,None,"People walking outdoors on a paved walkway.","People riding bicycles on a paved walkway.","Fish swimming underwater."),
    ("water","freenaturestock_video_catalog.json","rugged-ocean-coast","Ocean waves moving against a rocky coast.","A calm ocean with no visible waves at a rocky coast.","A campfire burning."),
    ("weather","freenaturestock_video_catalog.json","swift-moving-clouds","Clouds moving across the sky.","An empty clear sky without clouds.","People walking on a street."),
    ("fire","freenaturestock_video_catalog.json","campfire-embers","Glowing embers in a campfire.","Cold gray ashes without glowing embers.","Ocean waves breaking on the shore."),
    ("geology","usgs_public_domain_video_catalog.json","steamboat-geyser-yellowstone-national-park","A geyser emitting hot water or steam.","A quiet dry geyser vent without water or steam.","A person riding a bicycle."),
)
def source(case,directory,downloader):
    name,catalog,identifier,*_=case
    if catalog is None:
        from object_framing_audit import VIDEO_URL
        path=directory/"people.avi"
        fixture(path)
        return path,{"source":VIDEO_URL,"scope":"existing OpenCV test-only fixture"}
    data=json.loads((ROOT/"data"/catalog).read_text())
    if data["license_id"] not in ("CC0-1.0","PDM-1.0"):
        raise ValueError("catalog license not approved")
    clip=next(x for x in data["clips"] if x["id"]==identifier)
    if catalog.startswith("usgs") and clip.get("rights_statement")!="Public Domain":
        raise ValueError("missing public domain record")
    path=downloader.download(clip["video_url"])
    return path,{"source":clip["source_page"],"license":data["license_id"],"license_url":data["license_url"],"sha256":downloader.digest(path)}

def rank(rows,idx):
    if len(rows)!=3 or any(len(r)!=3 or not all(math.isfinite(float(v)) for v in r) for r in rows):
        raise ValueError("invalid score matrix")
    margins=[float(r[idx])-max(float(v) for j,v in enumerate(r) if j!=idx) for r in rows]
    return sum(m>0 for m in margins)>=2

def decision(rows,secondary,idx,moving,require_motion=False):
    a=rank(rows,idx)
    b=rank(secondary,idx)
    return {"clip":a,"siglip":b,"motion":moving,"require_motion":require_motion,
            "accepted":a and b and (moving if require_motion else True)}

def evaluate(frames,adjacent,queries,primary,secondary):
    rows=primary(frames,queries)
    other=secondary(frames,queries)
    motion=[motion_pair(a,b)["localized_change_observed"] for a,b in zip(frames,adjacent)]
    frozen=[motion_pair(a,a)["localized_change_observed"] for a in frames]
    moving=sum(motion)>=2
    # Repeat the first frame, exactly as in the frozen control.
    still=[frames[0]]*3
    still_rows=primary(still,queries)
    still_other=secondary(still,queries)
    tests=(("correct_subject",True,decision(rows,other,0,moving)),
           ("same_context_wrong_subject_or_action",False,decision(rows,other,1,moving)),
           ("unrelated_subject",False,decision(rows,other,2,moving)),
           ("frozen_motion_required",False,decision(still_rows,still_other,0,any(frozen),True)))
    return {name:{"expected":expected,"pass":d["accepted"]==expected,**d} for name,expected,d in tests}

def main():
    import torch
    from PIL import Image,ImageDraw
    from siglip_review import score
    torch.set_num_threads(2)
    out=Path("visual-ensemble-proof")
    out.mkdir(exist_ok=True)
    results={}
    matcher=SceneMatcher()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        downloader=VideoDownloader(root/"cache",max_bytes=180*1024*1024,total_timeout=90)
        for case in CASES:
            name=case[0]
            try:
                path,meta=source(case,root,downloader)
                times=(1.,2.,3.)
                frames=[_frame(path,t,448,preserve_aspect=True) for t in times]
                adjacent=[_frame(path,t+.24,448,preserve_aspect=True) for t in times]
                sheet=Image.new("RGB",(448,3*300),"white")
                draw=ImageDraw.Draw(sheet)
                for i,im in enumerate(frames):
                    thumbnail=im.copy()
                    thumbnail.thumbnail((448,270))
                    sheet.paste(thumbnail,((448-thumbnail.width)//2,i*300+20))
                    draw.text((8,i*300+4),f"{name}: {times[i]} sec",fill="black")
                sheet.save(out/(name+".jpg"),quality=88)
                rows=evaluate(frames,adjacent,list(case[3:]),matcher._similarities,score)
                result={"state":"evaluated","source":meta,"tests":rows,"provisional_labels":list(case[3:]),"sample_times":times}
            except Exception as exc:
                result={"state":"unavailable","error_type":type(exc).__name__,"error":str(exc)[:300]}
            results[name]=result
            print("ENSEMBLE CATEGORY",name,json.dumps(result),flush=True)
    evaluated=[r for r in results.values() if r["state"]=="evaluated"]
    tests=[v for r in evaluated for v in r["tests"].values()]
    summary={"planned":20,"evaluated":len(tests),"passed":sum(t["pass"] for t in tests),
             "false_accepts":sum(t["accepted"] and not t["expected"] for t in tests),
             "false_rejects":sum(not t["accepted"] and t["expected"] for t in tests),
             "unavailable_categories":5-len(evaluated),
             "scope":"5 source clips, 20 decisions, catalog-derived provisional labels; not 20 independent scenes or general production accuracy"}
    (out/"report.json").write_text(json.dumps({"categories":results,"summary":summary},indent=2))
    print("ENSEMBLE SUMMARY",json.dumps(summary),flush=True)
    return 0 if summary["passed"]==20 else 1
if __name__=="__main__":
    raise SystemExit(main())
