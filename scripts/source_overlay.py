"""Sample existing source text before our own captions are rendered.

Tesseract is a bounded heuristic: visible words are not guaranteed to be
recognized. Reject repeated high-confidence multi-word lines, not isolated
natural signs. No text is erased or masked.
"""
import csv
import io
import math
import os
import re
import subprocess
from collections import defaultdict

def line_evidence(tsv):
    lines=defaultdict(list)
    for row in csv.DictReader(io.StringIO(tsv),delimiter="\t"):
        try:
            word=str(row.get("text") or "").strip()
            if float(row["conf"])<70 or len(re.findall(r"[^\W\d_]",word))<3:
                continue
            key=tuple(row[k] for k in ("block_num","par_num","line_num"))
            lines[key].append(word)
        except (TypeError,ValueError,KeyError):
            continue
    return [len(v) for v in lines.values() if len(v)>=3]

def _read_frame(path,t,focus):
    vf=("scale=540:960:force_original_aspect_ratio=increase,"
        f"crop=540:960:x='max(0,min(iw-ow,iw*{focus:.5f}-ow/2))':y='(ih-oh)/2'")
    p=subprocess.run(["ffmpeg","-hide_banner","-nostdin","-v","error","-threads","2",
        "-ss",str(t),"-i",str(path),"-vf",vf,"-frames:v","1","-f","image2pipe",
        "-vcodec","png","-"],capture_output=True,check=True,timeout=8)
    if not p.stdout:
        raise ValueError("Source frame missing")
    return p.stdout

def _text(png):
    p=subprocess.run(["tesseract","stdin","stdout","-l","eng+deu","--psm","11","tsv"],
        input=png,capture_output=True,check=True,timeout=6,
        env={**os.environ,"OMP_THREAD_LIMIT":"1"})
    return line_evidence(p.stdout.decode("utf8",errors="replace"))

def check_source(path,seconds,focus=.5):
    if os.getenv("PURFFLE_SOURCE_TEXT_GATE")!="1":
        return {"state":"disabled"}
    seconds,focus=float(seconds),float(focus)
    if not math.isfinite(seconds) or seconds<=0 or not math.isfinite(focus) or not 0<=focus<=1:
        raise ValueError("Invalid source interval")
    try:
        times=[seconds*.1,seconds*.45,seconds*.8]
        evidence=[_text(_read_frame(path,t,focus)) for t in times]
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        raise RuntimeError("source_overlay_check_unavailable") from exc
    if sum(bool(row) for row in evidence)>=2:
        raise ValueError("source_overlay_text_detected: existing multi-word text in source frames")
    return {"state":"screened","text_frames":sum(bool(row) for row in evidence),
            "samples":len(evidence),"scope":"sampled English/German text, not guaranteed overlay absence"}
