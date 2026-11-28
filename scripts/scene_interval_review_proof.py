"""Targeted recheck of two reviewed sources. Preserve previous benchmark.
Frame observations are not full motion ground truth. No paid API or production imports.
"""
import json
import tempfile
from pathlib import Path
from media_validation import VideoDownloader
from visual_ensemble_proof import source
from visual_multitime_proof import FRESH,make_preview
from temporal_vision_pilot import local_engine,infer,parse_short_answer

REVIEW={
    "shore":{"sha256":"", "starts":[3.242488,17.4687,31.694912],
             "notes":["Stones dominate, dark water-like background; water visibility is limited."]*3,
             "questions":["Are rounded stones or rocks visibly present?","Is water visibly present behind or beside the rocks?","Is this a full-screen text card rather than camera footage?"]},
    "postfire":{"sha256":"","starts":[15.10324,66.8885,118.67376],
                "notes":["Full-screen green USGS introductory text card, no scene footage.",
                         "Forested channel with small possible debris flow; exact event visibility uncertain from sampled stills.",
                         "Clearly visible muddy debris in channel, consecutive frames show changed flow shape."],
                "questions":["Is muddy debris visibly flowing through a channel in the camera footage?","Is a forested channel visibly present?","Is this a full-screen text card rather than camera footage?"]},
}
def verdict(name,answers):
    if len(answers)!=3 or answers[2] is not False:
        return "reject_or_abstain"
    if answers[0] is True and answers[1] is True:
        return "candidate"
    return "reject_or_abstain"

def main():
    import torch
    torch.set_num_threads(2)
    out=Path("scene-interval-review")
    out.mkdir(exist_ok=True)
    results={}
    engine=local_engine("qwen2b")
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        downloader=VideoDownloader(root/"cache",max_bytes=180*1024*1024,total_timeout=90)
        for name,info in REVIEW.items():
            try:
                case=next(c for c in FRESH if c[0]==name)
                path,meta=source(case,root,downloader)
                if info["sha256"] and meta["sha256"]!=info["sha256"]:
                    raise ValueError("review source bytes changed")
                rows=[]
                for i,start in enumerate(info["starts"]):
                    clip=make_preview(path,root/"review.mp4",start,2.5)
                    answers=[]
                    raw=[]
                    for question in info["questions"]:
                        a=infer(engine,clip,question)
                        raw.append(a)
                        try:
                            answers.append(parse_short_answer(a))
                        except ValueError:
                            answers.append(None)
                    row={"start":start,"length":2.5,"answers":answers,"raw":raw,
                         "decision":verdict(name,answers),"review_note":info["notes"][i]}
                    rows.append(row)
                    print("INTERVAL REVIEW",name,json.dumps(row),flush=True)
                results[name]={"state":"evaluated","source":meta,"rows":rows}
            except Exception as exc:
                results[name]={"state":"unavailable","error":str(exc)[:300]}
    p=results.get("postfire",{}).get("rows",[])
    # Only clear extremes are scored. The middle and shoreline remain
    # diagnostic until interval-level ground truth is established.
    checks={"title_card_rejected":len(p)==3 and p[0]["decision"]!="candidate",
            "visible_flow_candidate":len(p)==3 and p[2]["decision"]=="candidate",
            "both_sources_evaluated":all(r.get("state")=="evaluated" for r in results.values())}
    report={"results":results,"checks":checks,
            "scope":"two targeted sources; only clear postfire intervals gated; no revised accuracy for original benchmark"}
    (out/"report.json").write_text(json.dumps(report,indent=2))
    print("INTERVAL REVIEW SUMMARY",json.dumps(checks),flush=True)
    return 0 if all(checks.values()) else 1
if __name__=="__main__":
    raise SystemExit(main())
