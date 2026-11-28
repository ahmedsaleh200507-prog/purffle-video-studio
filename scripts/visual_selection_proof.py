"""Isolated real-pixel proof of the existing production visual gates.

No production changes, no paid services, no generated footage. Metadata is
deliberately identical for positive and negative pixel tests of each request.
A score is a heuristic, not visual truth or evidence of semantic motion.
"""
import json
from pathlib import Path
import tempfile

from media_validation import SceneMatcher, SceneSpec, ValidationError, _frame
from real_visual_suite import prepare_fixtures, sha256, CASES
from visual_director import inspect_action
from event_theme_review import motion_pair

def specs():
    return {
        "people":SceneSpec(main_character="people",object="people",action="walking",
                           location="paved walkway",time="daylight",
                           visual_search_query="people walking outdoors on a paved walkway"),
        "fish":SceneSpec(main_character="",object="fish",action="swimming",
                         location="sea",time="daylight",visual_search_query="fish swimming underwater in the sea"),
        "whale":SceneSpec(main_character="",object="whale",action="swimming",
                          location="sea",time="daylight",visual_search_query="whale swimming underwater in the sea"),
        "wrong_action":SceneSpec(main_character="people",object="people",action="riding bicycles",
                                 location="paved walkway",time="daylight",
                                 visual_search_query="people riding bicycles on a paved walkway"),
    }

def match_case(matcher,path,spec,expected,*,duration=3.0):
    # The false clip gets exactly the same plausible metadata as the true clip.
    metadata=spec.visual_search_query
    try:
        report=matcher.match(path,spec,metadata,duration=duration)
        accepted=True
    except ValidationError as exc:
        report={"rejection":str(exc)}
        accepted=False
    return {"accepted":accepted,"expected":expected,"pass":accepted==expected,
            "metadata":metadata,"evidence":report}

def action_case(frames,expected,scorer):
    contract={"family":"generic","event_required":True,
              "positive":"People riding bicycles on a paved walkway.",
              "negative":"People walking on a paved walkway without bicycles."}
    report=inspect_action(None,3.0,.5,contract,frames=frames,scorer=scorer,opening=True)
    return {"accepted":report["verified"],"expected":expected,
            "pass":report["verified"]==expected,"evidence":report,
            "scope":"negative same-subject action control; frame similarity alone cannot certify motion"}

def main():
    import torch
    from PIL import Image, ImageDraw
    torch.set_num_threads(2)
    out=Path("visual-selection-proof")
    out.mkdir(exist_ok=True)
    report={"cases":{},"scope":"Known clips and hard negative controls only. Not general accuracy or production approval."}
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        prepare_fixtures(root)
        manifest=json.loads((root/"manifest.json").read_text())
        report["fixtures"]=manifest
        available={}
        for name,entry in manifest.items():
            if entry.get("state")!="ready":
                continue
            path=root/(name+(".avi" if name=="people" else ".webm"))
            if not path.is_file() or sha256(path)!=entry["sha256"]:
                raise ValueError("fixture integrity mismatch")
            available[name]=path
            frames=[_frame(path,t,640,preserve_aspect=True) for t in (.2,1.2,2.7)]
            sheet=Image.new("RGB",(640,3*400),"#ffffff")
            draw=ImageDraw.Draw(sheet)
            for i,frame in enumerate(frames):
                frame.thumbnail((640,370))
                sheet.paste(frame,((640-frame.width)//2,400*i+25))
                draw.text((8,400*i+5),f"{name}: {(.2,1.2,2.7)[i]} sec",fill="#111111")
            sheet.save(out/(name+"-frames.jpg"),quality=88)
        matcher=SceneMatcher()
        requests=specs()
        tests=[("people_correct","people","people",True),
               ("whale_wrong_pixels","people","whale",False),
               ("same_subject_wrong_action","people","wrong_action",False),
               ("fish_correct","fish","fish",True),
               ("fish_wrong_pixels","people","fish",False),
               ("people_wrong_pixels","fish","people",False)]
        for label,clip,target,expected in tests:
            if clip not in available:
                row={"state":"unavailable","expected":expected}
            else:
                try:
                    row=match_case(matcher,available[clip],requests[target],expected)
                    row["state"]="evaluated"
                except Exception as exc:
                    row={"state":"error","error_type":type(exc).__name__,"error":str(exc)[:300]}
            row.update(clip=clip,request=target)
            report["cases"][label]=row
            print("VISUAL SELECTION",label,json.dumps(row,ensure_ascii=False),flush=True)
        if "people" in available:
            frames=[_frame(available["people"],t,448,preserve_aspect=True) for t in (.2,1.2,2.0)]
            try:
                row=action_case(frames,False,matcher._similarities)
                row["state"]="evaluated"
            except Exception as exc:
                row={"state":"error","error_type":type(exc).__name__,"error":str(exc)[:300]}
            report["cases"]["director_wrong_action"]=row
            print("VISUAL SELECTION director_wrong_action",json.dumps(row),flush=True)
            try:
                first=frames[0]
                adjacent=_frame(available["people"],.44,448,preserve_aspect=True)
                moving=motion_pair(first,adjacent)
                frozen=motion_pair(first,first)
                row={"state":"evaluated","pass":bool(moving["localized_change_observed"]) and not frozen["localized_change_observed"],
                     "moving":moving,"frozen":frozen,"scope":"actual motion versus frozen frame, not action semantics"}
            except Exception as exc:
                row={"state":"error","error_type":type(exc).__name__,"error":str(exc)[:300]}
            report["cases"]["motion_vs_frozen"]=row
            print("VISUAL SELECTION motion_vs_frozen",json.dumps(row),flush=True)
        else:
            for label in ("director_wrong_action","motion_vs_frozen"):
                report["cases"][label]={"state":"unavailable"}
    rows=list(report["cases"].values())
    report["summary"]={"planned":len(rows),"evaluated":sum(r["state"]=="evaluated" for r in rows),
                       "passed":sum(r.get("pass") is True for r in rows),
                       "failed":sum(r["state"]=="evaluated" and r.get("pass") is False for r in rows),
                       "unavailable":sum(r["state"]=="unavailable" for r in rows),
                       "errors":sum(r["state"]=="error" for r in rows)}
    (out/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("VISUAL SELECTION SUMMARY",json.dumps(report["summary"]),flush=True)
    return 0 if report["summary"]["passed"]==len(rows) else 1

if __name__=="__main__":
    raise SystemExit(main())
