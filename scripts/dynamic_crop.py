"""Render bounded, independently screened horizontal crop proposals.

No identity guarantee. Preserve the static path if a derived clip fails.
"""
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path

def tracking_filter(width,height,proposal,duration):
    if proposal.get("state")!="shadow_proposal":
        raise ValueError("No eligible track")
    points=proposal.get("keyframes",[])
    if not 3<=len(points)<=12 or not math.isfinite(duration) or duration<=0:
        raise ValueError("Invalid tracking length")
    ts=[float(p["time"]) for p in points]
    xs=[float(p["focus_x"]) for p in points]
    coverage = [float(proposal.get(k, default)) for k, default in (
        ("min_tracked_coverage", 0), ("tracked_coverage", 0), ("fixed_coverage", 1))]
    if (not all(math.isfinite(v) and 0 <= v <= 1 for v in coverage)
        or not all(math.isfinite(t) and 0<=t<=duration for t in ts)
        or not all(math.isfinite(x) and 0<=x<=1 for x in xs)
        or any(b<=a for a,b in zip(ts,ts[1:]))
        or any(abs(b-a)>.31*(u-t)+.001 for a,b,t,u in zip(xs,xs[1:],ts,ts[1:]))
        or ts[0]>.5 or duration-ts[-1]>max(.5,duration*.2)
        or coverage[0]<.8
        or coverage[1]-coverage[2]<.099):
        raise ValueError("Track does not satisfy coverage and speed bounds")
    value=f"{xs[-1]:.6f}"
    for i in reversed(range(len(ts)-1)):
        start,end=ts[i:i+2]
        x,y=xs[i:i+2]
        interp=f"({x:.6f}+({y-x:.6f})*(t-{start:.6f})/{end-start:.6f})"
        value=f"if(lt(t,{end:.6f}),{interp},{value})"
    value=f"if(lt(t,{ts[0]:.6f}),{xs[0]:.6f},{value})"
    w,h=int(width),int(height)
    if min(w,h)<=0 or w%2 or h%2:
        raise ValueError("Invalid output dimensions")
    return (f"setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={w}:{h}:x='max(0,min(iw-ow,iw*({value})-ow/2))':y='(ih-oh)/2',setsar=1")

def render_tracked(path,proposal,duration,width,height,*,deadline):
    remaining=deadline-time.monotonic()
    if remaining<20:
        raise TimeoutError("Dynamic crop budget unavailable")
    vf=tracking_filter(width,height,proposal,duration)
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix="tracked-",suffix=".mp4",dir=path.parent)
    os.close(fd)
    target=Path(name)
    try:
        result=subprocess.run(["ffmpeg","-hide_banner","-nostdin","-y","-v","error",
            "-threads","2","-filter_threads","1","-i",str(path),"-t",f"{duration+.12:.3f}",
            "-map","0:v:0","-an","-vf",vf+",format=yuv420p","-c:v","libx264",
            "-preset","veryfast","-crf","18","-threads","2",str(target)],
            capture_output=True,timeout=min(65.,remaining))
        if result.returncode or target.stat().st_size<1024:
            raise RuntimeError("Dynamic crop encoding failed")
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise
