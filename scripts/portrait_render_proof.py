"""Actual FFmpeg portrait render audit on known test-only footage and CC0 scenery.
Detection coverage is model-derived, not human annotation. No dynamic identity
claims, no voice changes, no production writes or paid inference.
"""
import json
import math
import statistics
import subprocess
import tempfile
from pathlib import Path
from media_validation import SceneMatcher, VideoDownloader, _frame
from visual_ensemble_proof import CASES,source
from object_framing import detect,stable_focus,group_focus
from object_region_review import corroborate
from visual_crop_integrity import assess_portrait_pillarbox

def probe(path):
    data=json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_entries",
        "stream=width,height,avg_frame_rate:format=duration","-of","json",str(path)],text=True,timeout=30))
    stream=data["streams"][0]
    return int(stream["width"]),int(stream["height"]),float(data["format"]["duration"])

def crop_geometry(w,h,focus):
    if min(w,h)<2 or not math.isfinite(focus):
        raise ValueError("invalid crop geometry")
    if w/h>=9/16:
        ch=h//2*2
        cw=max(2,int(ch*9/16)//2*2)
    else:
        cw=w//2*2
        ch=max(2,int(cw*16/9)//2*2)
    x=max(0,min(w-cw,int(w*focus-cw/2)))//2*2
    y=max(0,(h-ch)//2)//2*2
    return cw,ch,x,y

def coverage(rows,w,geom):
    cw,_,x,_=geom
    left,right=x/w,(x+cw)/w
    scores=[]
    for row in rows:
        if not row:
            continue
        vals=[]
        for d in row:
            a,_,b,_=d["box"]
            if b>a:
                vals.append(max(0.,min(right,b)-max(left,a))/(b-a))
        if vals:
            scores.append(max(vals))
    return {"frames":len(scores),"mean":statistics.mean(scores) if scores else None,
            "minimum":min(scores) if scores else None}

def render(path,target,start,length,geom):
    cw,ch,x,y=geom
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-ss",str(start),
        "-i",str(path),"-t",str(length),"-vf",
        f"crop={cw}:{ch}:{x}:{y},scale=1080:1920:flags=lanczos,setsar=1,fps=30",
        "-an","-c:v","libx264","-preset","fast","-crf","20","-pix_fmt","yuv420p","-movflags","+faststart",str(target)],
        check=True,timeout=120)

def main():
    import torch
    from PIL import Image
    from siglip_review import score
    torch.set_num_threads(2)
    out=Path("portrait-render-proof")
    out.mkdir(exist_ok=True)
    results={}
    matcher=SceneMatcher()
    # Exact previously tested starts; no claim of final production approval.
    choices=(("people",8.29,"person"),("water",.55680496,None),("fire",11.2958665,None))
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        downloader=VideoDownloader(root/"cache",max_bytes=180*1024*1024,total_timeout=90)
        for name,start,subject in choices:
            try:
                case=next(c for c in CASES if c[0]==name)
                path,meta=source(case,root,downloader)
                w,h,duration=probe(path)
                length=2.5
                if start+length>duration:
                    raise ValueError("interval outside source")
                times=(.35,1.25,2.1)
                frames=[_frame(path,start+t,640,preserve_aspect=True) for t in times]
                rows=[]
                focus=.5
                proposal={"state":"center_for_scenery"}
                if subject:
                    rows=[corroborate(f,subject,detect(f,subject),scorer=matcher._similarities)["accepted"] for f in frames]
                    fraction=min(1.,h*9/(w*16))
                    proposal=group_focus(rows,fraction) if sum(len(r)>=2 for r in rows)>=2 else stable_focus(rows,fraction)
                    focus=proposal["focus_x"]
                center=crop_geometry(w,h,.5)
                geom=crop_geometry(w,h,focus)
                base,chosen=coverage(rows,w,center),coverage(rows,w,geom)
                # Fall back to center if proposal hurts visible-box coverage.
                if subject and chosen["mean"] is not None and base["mean"] is not None and chosen["mean"]<base["mean"]:
                    geom=center
                    chosen=base
                    proposal={"state":"keep_center_coverage"}
                target=out/(name+".mp4")
                render(path,target,start,length,geom)
                ow,oh,od=probe(target)
                crops=[_frame(target,t,640,preserve_aspect=True) for t in times]
                integrity=assess_portrait_pillarbox(crops)
                queries=list(case[3:])
                def matches(rows):
                    return sum(r[0]>max(r[1:]) for r in rows)>=2
                semantic={"clip":matches(matcher._similarities(crops,queries)),
                          "siglip":matches(score(crops,queries))}
                # Three source and rendered image pairs for direct review.
                sheet=Image.new("RGB",(960,3*400),"white")
                for i,(a,b) in enumerate(zip(frames,crops)):
                    a=a.copy();b=b.copy()
                    a.thumbnail((640,390));b.thumbnail((300,390))
                    sheet.paste(a,(0,i*400))
                    sheet.paste(b,(650,i*400))
                sheet.save(out/(name+"-comparison.jpg"),quality=88)
                checks={"full_hd_portrait":(ow,oh)==(1080,1920),
                        "duration_preserved":abs(od-length)<=.12,
                        "border_integrity":integrity["verified"],
                        "semantic_after_crop":all(semantic.values()),
                        "subject_coverage":not subject or (chosen["frames"]>=2 and chosen["mean"]>=.8 and chosen["minimum"]>=.6)}
                result={"state":"evaluated","source":meta,"interval":[start,length],"source_size":[w,h],
                        "output_size":[ow,oh],"output_duration":od,"proposal":proposal,"crop":geom,
                        "center_coverage":base,"chosen_coverage":chosen,"semantic":semantic,"integrity":integrity,
                        "checks":checks,"pass":all(checks.values())}
            except Exception as exc:
                result={"state":"unavailable","error":str(exc)[:300],"pass":False}
            results[name]=result
            print("PORTRAIT RENDER",name,json.dumps(result),flush=True)
    summary={"planned":len(choices),"passed":sum(r["pass"] for r in results.values()),
             "scope":"3 real rendered silent excerpts; model-derived coverage; no dynamic tracking or finished Shorts approval"}
    (out/"report.json").write_text(json.dumps({"results":results,"summary":summary},indent=2))
    print("PORTRAIT SUMMARY",json.dumps(summary),flush=True)
    return 0 if summary["passed"]==len(choices) else 1
if __name__=="__main__":
    raise SystemExit(main())
