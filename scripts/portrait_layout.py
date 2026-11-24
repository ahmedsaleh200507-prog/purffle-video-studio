"""Honest 9:16 composition for real HD sources that cannot fill a native crop."""
import hashlib
import math
import os
import subprocess
import tempfile
from pathlib import Path
from media_validation import portrait_crop_allowed, portrait_crop_limit, ValidationError

def plan_portrait(width,height,W,H,*,allow_context=True):
    width,height,W,H=map(int,(width,height,W,H))
    if min(width,height)<720 or min(W,H)<=0:
        return None
    scale=max(W/width,H/height)
    if portrait_crop_allowed(scale):
        return {"mode":"subject_crop","source_width":width,"source_height":height,
                "crop_scale":round(scale,5)}
    if not allow_context:
        return None
    # Foreground retains all original content and never exceeds the existing
    # sharp-pixel enlargement limit. The soft backdrop is decorative only.
    fit=min(W/width,H/height,portrait_crop_limit())
    fw=max(2,int(width*fit)//2*2)
    fh=max(2,int(height*fit)//2*2)
    return {"mode":"full_frame_context","source_width":width,"source_height":height,
            "foreground_width":fw,"foreground_height":fh,
            "foreground_scale":round(max(fw/width,fh/height),5),
            "background":"same_video_soft_blur","crop_scale_if_fullscreen":round(scale,5),
            "output_width":W,"output_height":H,"native_fullscreen":False}

def context_enabled():
    return os.environ.get("PURFFLE_SHORTS_CONTEXT_LAYOUT","0")=="1"

def render_context(path,plan,seconds,fps=30):
    if plan.get("mode")!="full_frame_context":
        raise ValidationError("Invalid context composition")
    W,H=plan["output_width"],plan["output_height"]
    fw,fh=plan["foreground_width"],plan["foreground_height"]
    if not math.isfinite(seconds) or not .6<=seconds<=90:
        raise ValidationError("Invalid context duration")
    path=Path(path)
    # Make actual video composition, not a simulated new source resolution.
    # A cheap quarter-size blurred background avoids wasting CI CPU.
    bw,bh=max(2,W//8*2),max(2,H//8*2)
    vf=(f"[0:v]split=2[bg][fg];[bg]scale={bw}:{bh}:force_original_aspect_ratio=increase,"
        f"crop={bw}:{bh},gblur=sigma=12,eq=brightness=-0.09:saturation=0.8,"
        f"scale={W}:{H}:flags=bilinear,setsar=1[back];"
        f"[fg]scale={fw}:{fh}:flags=lanczos,setsar=1[front];"
        f"[back][front]overlay=(W-w)/2:(H-h)/2:shortest=1,fps={int(fps)},format=yuv420p[v]")
    key=hashlib.sha256((str(path.resolve())+str(path.stat().st_size)+str(plan)+str(seconds)).encode()).hexdigest()
    target=path.parent/(key+".portrait.mp4")
    fd,name=tempfile.mkstemp(dir=path.parent,suffix=".portrait.part.mp4")
    os.close(fd)
    try:
        r=subprocess.run(["ffmpeg","-hide_banner","-nostdin","-y","-v","error",
            "-threads","2","-filter_complex_threads","1","-i",str(path),
            "-filter_complex",vf,"-map","[v]","-an","-sn","-dn","-t",f"{seconds:.3f}",
            "-c:v","libx264","-preset","veryfast","-crf","20","-threads","2",
            "-movflags","+faststart",name],capture_output=True,timeout=100)
        if r.returncode or Path(name).stat().st_size<1024:
            raise ValidationError("Portrait context composition failed")
        Path(name).replace(target)
        return target
    except subprocess.TimeoutExpired:
        raise ValidationError("Portrait context composition timed out") from None
    finally:
        Path(name).unlink(missing_ok=True)
