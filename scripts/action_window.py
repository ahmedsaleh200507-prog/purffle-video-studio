"""Bounded action-oriented source trim, before ordinary footage gates.

Uses existing CLIP event screening as comparative evidence, not action ground
truth. The actual extracted interval still goes through every production gate.
"""
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path

def select_window(path, duration, need, contract, *, scorer, deadline, inspector=None, opening=True):
    if not contract or not contract.get("event_required"):
        return {"state":"not_required","offset":0.}
    if not all(math.isfinite(float(v)) for v in (duration,need)) or need<1 or duration<need+2:
        return {"state":"no_extra_duration","offset":0.}
    if inspector is None:
        from visual_director import inspect_action
        inspector=inspect_action
    # Use actual 9:16 centre preview; final chosen crop is rechecked independently.
    # Preserve early fast paths, then look across the available clip. At most
    # six previews; every extracted window still needs the full validators.
    tail=max(0.,float(duration)-float(need)-.2)
    offsets=list(dict.fromkeys(round(v,3) for v in
        (0.,min(3.,tail),min(9.,tail),tail/2,tail*.75,tail)))
    attempts=[]
    from visual_director import _frame_at
    for offset in offsets:
        if time.monotonic()+12>=deadline:
            break
        try:
            # Frame timestamps exactly mirror the final opening check.
            times=[offset+min(.4,need*.1),offset+min(1.7,need*.35),offset+need*.66]
            frames=[_frame_at(path,t,.5) for t in times]
            result=inspector(path,need,.5,contract,scorer=scorer,frames=frames,opening=opening)
            attempts.append({"offset":offset,"verified":bool(result.get("verified")),
                             "margin":result.get("best_action_margin")})
            if result.get("verified"):
                return {"state":"keep_start" if offset==0 else "later_interval_proposed",
                        "offset":offset,"attempts":attempts}
        except Exception as exc:
            attempts.append({"offset":offset,"error_type":type(exc).__name__})
            continue
    return {"state":"no_verified_later_interval","offset":0.,"attempts":attempts}

def extract_window(path, offset, need, *, deadline):
    """Materialize the interval so downstream timestamps remain zero-based."""
    if not math.isfinite(offset) or not math.isfinite(need) or offset<=0 or need<1:
        raise ValueError("Invalid source trim")
    remaining=deadline-time.monotonic()
    if remaining<15:
        raise TimeoutError("No trim budget")
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix="verified-window-",suffix=".mp4",dir=path.parent)
    os.close(fd)
    target=Path(name)
    try:
        p=subprocess.run(["ffmpeg","-hide_banner","-nostdin","-y","-v","error",
            "-threads","2","-filter_threads","1","-ss",f"{offset:.3f}",
            "-i",str(path),"-t",f"{need+.12:.3f}","-map","0:v:0","-an",
            "-c:v","libx264","-preset","veryfast","-crf","18","-threads","2",
            "-pix_fmt","yuv420p",str(target)],capture_output=True,
            timeout=min(45.,remaining))
        if p.returncode or target.stat().st_size<1024:
            raise RuntimeError("Source trim encoding failed")
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise
