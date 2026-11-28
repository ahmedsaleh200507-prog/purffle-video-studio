"""Exact-frame assembly of independently approved, distinct moving shots.
Opt-in building block; not yet called by the live Shorts pipeline.
"""
import hashlib
import json
import math
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

def frame_plan(seconds,fps=30):
    if not math.isfinite(seconds) or not 4<=seconds<=15 or not 15<=fps<=60:
        raise ValueError("invalid scene duration")
    total=math.ceil(seconds*fps)
    count=2 if total<=8*fps else 3
    base,rest=divmod(total,count)
    return [base+int(i<rest) for i in range(count)]

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def probe(path):
    data=json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0",
        "-count_frames","-show_entries","stream=width,height,avg_frame_rate,nb_read_frames:format=duration",
        "-of","json",str(path)],text=True,timeout=45))
    s=data["streams"][0]
    return {"width":int(s["width"]),"height":int(s["height"]),"fps":float(Fraction(s["avg_frame_rate"])),
            "frames":int(s["nb_read_frames"]),"duration":float(data["format"]["duration"])}

def validate_plan(shots,counts,fps):
    from video_sources import LicenseValidator
    if not 2<=len(shots)<=3 or len(shots)!=len(counts):
        raise ValueError("two or three distinct approved shots required")
    seen=set()
    for row,n in zip(shots,counts):
        h=row.get("sha256")
        if not isinstance(h,str) or len(h)!=64 or any(c not in "0123456789abcdef" for c in h) or h in seen:
            raise ValueError("duplicate or missing source hash")
        seen.add(h)
        if not LicenseValidator.validate(row.get("license")) or not row.get("id"):
            raise ValueError("missing source provenance")
        if type(n) is not int or n<2*fps or n>6*fps:
            raise ValueError("invalid shot length")
        start=float(row["start"])
        if not math.isfinite(start) or start<0:
            raise ValueError("invalid source start")
        if row.get("approval",{}).get("verified") is not True:
            raise ValueError("source interval not independently approved")
        if abs(float(row["approval"]["start"])-start)>1e-6 or abs(float(row["approval"]["seconds"])-n/fps)>1e-6:
            raise ValueError("approval is for a different interval")
        if row["approval"].get("sha256")!=h:
            raise ValueError("approval is for different source bytes")

def assemble(shots,counts,target,*,width=1080,height=1920,fps=30,review):
    """Recheck each actual portrait shot and join without stretching or looping.
    review(path,seconds,row) must verify the rendered interval independently.
    The callback is mandatory; technical checks alone cannot approve a subject.
    """
    from media_validation import QualityValidator,_frame
    from portrait_layout import focus_filter,plan_portrait
    from visual_crop_integrity import assess_portrait_pillarbox
    validate_plan(shots,counts,fps)
    if not callable(review):
        raise ValueError("missing independent output review")
    target=Path(target)
    if target.exists():
        raise ValueError("refusing to overwrite existing video")
    target.parent.mkdir(parents=True,exist_ok=True)
    validator=QualityValidator()
    rows=[]
    try:
        with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
            root=Path(tmp)
            parts=[]
            for i,(row,n) in enumerate(zip(shots,counts)):
                path=Path(row["path"])
                start=float(row["start"])
                length=n/fps
                focus=float(row.get("focus",.5))
                if digest(path)!=row["sha256"]:
                    raise ValueError("source bytes changed after approval")
                # Probe real native dimensions before any scaling. Never allow
                # an assembled HD file to conceal low-resolution components.
                source=validator.validate(path)
                if plan_portrait(source["width"],source["height"],width,height) is None:
                    raise ValueError("native source cannot satisfy portrait crop")
                if start+length>source["duration"]+.001:
                    raise ValueError("source too short; no loops or freeze frames")
                part=root/f"shot-{i}.mp4"
                subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-threads","2",
                    "-filter_threads","1","-ss",str(start),"-i",str(path),"-an",
                    "-vf",f"{focus_filter(width,height,focus)},fps={fps},format=yuv420p",
                    "-frames:v",str(n),"-c:v","libx264","-preset","veryfast","-crf","18","-threads","2",str(part)],
                    check=True,timeout=100)
                measured=probe(part)
                if (measured["width"],measured["height"],measured["frames"])!=(width,height,n) or abs(measured["fps"]-fps)>.05:
                    raise ValueError("rendered shot frame count or format mismatch")
                quality=validator.validate(part,need=length-.04)
                frames=[_frame(part,length*f,448,preserve_aspect=True) for f in (.15,.50,.85)]
                if not assess_portrait_pillarbox(frames)["verified"]:
                    raise ValueError("invalid portrait borders")
                proof=review(part,length,row)
                if proof.get("verified") is not True:
                    raise ValueError("rendered shot failed independent semantic review")
                rows.append({k:v for k,v in row.items() if k!="path"}|
                    {"start_frame":sum(counts[:i]),"frames":n,"seconds":length,
                     "native_source_size":[source["width"],source["height"]],
                     "portrait_quality":quality,"post_crop_review":proof,"output_sha256":digest(part)})
                parts.append(part)
            listing=root/"concat.txt"
            listing.write_text("".join(f"file '{p.name}'\n" for p in parts))
            subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-f","concat",
                "-safe","1","-i",str(listing),"-c","copy","-movflags","+faststart",str(target)],check=True,timeout=60)
            measured=probe(target)
            if (measured["width"],measured["height"],measured["frames"])!=(width,height,sum(counts)) or abs(measured["fps"]-fps)>.05:
                raise ValueError("joined scene timeline mismatch")
            if abs(measured["duration"]-sum(counts)/fps)>1/fps:
                raise ValueError("joined duration mismatch")
            validator.validate(target,need=sum(counts)/fps-.04)
            # Recheck every component in the actual joined video as well.
            for row in rows:
                start=row["start_frame"]/fps
                part=root/"joined-check.mp4"
                subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-ss",str(start),
                    "-i",str(target),"-an","-frames:v",str(row["frames"]),"-c:v","libx264",
                    "-preset","veryfast","-crf","18","-threads","2",str(part)],check=True,timeout=60)
                if probe(part)["frames"]!=row["frames"]:
                    raise ValueError("joined interval is incomplete")
                row["joined_review"]=review(part,row["seconds"],row)
                if row["joined_review"].get("verified") is not True:
                    raise ValueError("joined interval lost subject")
            return {"state":"verified_bundle","shots":rows,"frames":sum(counts),"duration":measured["duration"],
                    "output":measured,"sha256":digest(target),"scope":"silent real-footage assembly; no narration or retention claim"}
    except BaseException:
        target.unlink(missing_ok=True)
        raise
