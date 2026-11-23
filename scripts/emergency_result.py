"""Last-resort ACTUAL MP4 creator for CI setup, LLM or source failures.

Called from an always-on CI step BEFORE artifacts are uploaded.
Independent of torch, CLIP, PEXELS, Gemini, Groq and Piper.
Creates a FULL 32-second Short or 602-second long film, NOT a preview.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from offline_video import make_video


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError, TypeError):
        return {}


def shorts(index, raw):
    from batch import parse_topic, write_json
    language, topic = parse_topic(raw)
    out=Path("finished")/f"video_{index:02d}"
    out.mkdir(parents=True,exist_ok=True)
    report_path=out/"report.json"
    old=_read(report_path)
    if old.get("status")=="ok" and old.get("mp4"):
        existing=Path(old["mp4"])
        if existing.is_file() and existing.stat().st_size>1024:
            print("[EMERGENCY] Existing normal or fallback Shorts MP4 preserved")
            return old
    result=make_video(topic=topic,language=language,mode="short",
                      output=out/"fallback-video.mp4",root=out)
    for p in out.rglob("*.mp4"):
        if p.resolve()!=(out/"fallback-video.mp4").resolve():
            p.unlink(missing_ok=True)
    result.update({
        "index":index,"topic":topic,"original_input":raw,
        "language":language,"stage":"complete_offline_fallback",
        "earlier_pipeline_error":str(old.get("error",""))[:350],
        "render_origin":"standalone_offline_ci_emergency",
    })
    write_json(report_path,result)
    print(f"[FULL SHORT MP4 AVAILABLE] {result['mp4']}",flush=True)
    return result


def long(raw,language):
    from batch import write_json
    out=Path("long_video_output/result")
    out.mkdir(parents=True,exist_ok=True)
    report_path=out/"report.json"
    old=_read(report_path)
    if old.get("status")=="ok" and (out/"long-video.mp4").is_file():
        print("[EMERGENCY] Existing complete long MP4 preserved")
        return old
    result=make_video(topic=raw,language=language,mode="long",
                      output=out/"long-video.mp4",root=out)
    (out/"PREVIEW_INCOMPLETE.mp4").unlink(missing_ok=True)
    result.update({
        "mp4":"long-video.mp4","mode":"long_video","topic":raw,
        "language":language,"stage":"complete_offline_fallback",
        "earlier_pipeline_error":str(old.get("error",""))[:350],
        "burnt_in_subtitles":False,
        "subtitle_track":"separate_srt_sidecar_only",
        "render_origin":"standalone_offline_ci_emergency",
    })
    write_json(report_path,result)
    write_json(out/"output-qa.json",{
        "mode":"offline_2d_fallback","mp4_verified":"ffprobe",
        "duration":result["duration"],
    })
    print(f"[FULL LONG MP4 AVAILABLE] {out/'long-video.mp4'}",flush=True)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("short","long"),required=True)
    p.add_argument("--topic",required=True)
    p.add_argument("--language",default="en",choices=("en","de"))
    p.add_argument("--slot",type=int,default=1)
    a=p.parse_args()
    if a.mode=="short":
        if not 1<=a.slot<=10:
            raise ValueError("Invalid Shorts slot")
        shorts(a.slot,a.topic)
    else:
        long(a.topic,a.language)


if __name__=="__main__":
    main()
