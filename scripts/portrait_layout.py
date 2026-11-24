"""Centered full-screen portrait crop, never padding or blurred backgrounds."""
import os
import math
import subprocess
from pathlib import Path
from media_validation import portrait_crop_allowed, ValidationError

def center_enabled():
    return os.environ.get("PURFFLE_SHORTS_CENTER_CROP","0")=="1"

def plan_portrait(width,height,W,H):
    width,height,W,H=map(int,(width,height,W,H))
    if min(width,height)<720 or min(W,H)<=0:
        return None
    scale=max(W/width,H/height)
    if not portrait_crop_allowed(scale):
        return None
    return {"mode":"center_crop" if center_enabled() else "subject_crop",
            "source_width":width,"source_height":height,
            "output_width":W,"output_height":H,"crop_scale":round(scale,5),
            "native_fullscreen":scale<=1,"upscaled":scale>1.0001,
            "effective_source_width":round(min(width,height*W/H)),
            "effective_source_height":round(min(height,width*H/W))}

def center_filter(W,H):
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={W}:{H}:x='(iw-ow)/2':y='(ih-oh)/2',setsar=1")

def render_center_sample(path,plan,seconds,fps=30):
    W,H=plan["output_width"],plan["output_height"]
    if not math.isfinite(seconds) or not .6<=seconds<=90:
        raise ValidationError("Invalid sample duration")
    path=Path(path)
    target=path.with_name(path.stem+".center-sample.mp4")
    r=subprocess.run(["ffmpeg","-hide_banner","-nostdin","-y","-v","error",
        "-threads","2","-filter_threads","1","-i",str(path),"-t",str(seconds),
        "-an","-vf",f"{center_filter(W,H)},fps={int(fps)},format=yuv420p",
        "-c:v","libx264","-preset","veryfast","-crf","20","-threads","2",str(target)],
        capture_output=True,timeout=100)
    if r.returncode or not target.exists() or target.stat().st_size<1024:
        raise ValidationError("Centered portrait sample failed")
    return target
