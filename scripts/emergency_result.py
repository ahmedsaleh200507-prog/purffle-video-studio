"""Recover failed CI jobs honestly.

Shorts: generate full offline 2D video when the normal pipeline fails.
Long films: preserve independently screened, completed chapters if possible,
but do not counterfeit 10 minutes with repeated slides and silent padding.
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
    if old.get("status") in ("ok","review") and old.get("mp4"):
        existing=Path(old["mp4"])
        if existing.is_file() and existing.stat().st_size>1024:
            print("[EMERGENCY] Existing normal or fallback Shorts MP4 preserved")
            return old
    import os
    if os.environ.get("PURFFLE_REAL_ONLY_RECOVERY")=="1":
        from short_recovery import recover_short
        try:
            result=recover_short(topic,language,out)
        except Exception as exc:
            old.update(status="failed",mp4=None,recovery_error=type(exc).__name__+": "+str(exc)[:250])
            write_json(report_path,old)
            raise
    else:
        result=make_video(topic=topic,language=language,mode="short",
                          output=out/"fallback-video.mp4",root=out)
    for p in out.rglob("*.mp4"):
        if p.resolve()!=Path(result["mp4"]).resolve():
            p.unlink(missing_ok=True)
    result.update({
        "index":index,"topic":topic,"original_input":raw,
        "language":language,"stage":"mixed_media_review" if result.get("status")=="review" else "complete_offline_fallback",
        "earlier_pipeline_error":str(old.get("error",""))[:350],
        "render_origin":"standalone_offline_ci_emergency",
    })
    write_json(report_path,result)
    print(f"[FULL SHORT MP4 AVAILABLE] {result['mp4']}",flush=True)
    return result


def long(raw, language):
    """Recover real recorded chapters, never invent a 10-minute documentary.

    On source/LLM failure we can deliver genuinely finished chapters as a
    separately marked partial MP4. It is not a completed 10-minute movie.
    The old 602-second offline slideshow repeated seven facts and padded
    forty-second silence; it must never be reported as success.
    """
    from batch import write_json
    import subprocess
    out = Path("long_video_output/result")
    work = Path("long_video_output/work")
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "report.json"
    report = _read(report_path)
    qa = _read(out / "documentary-quality.json")
    finished = out / "long-video.mp4"
    if (report.get("status") in ("ok","review") and report.get("mp4") == "long-video.mp4"
            and finished.is_file() and finished.stat().st_size > 1000
            and _read(out/"output-qa.json").get("state")=="passed"):
        print("[LONG MP4 PRESERVED] quality status:", report.get("status"), flush=True)
        return report
    if (report.get("status") == "ok"
            and qa.get("publication_quality") == "narrated_real_footage_validated"
            and finished.is_file()):
        print("[LONG VERIFIED] genuine 10-minute documentary preserved")
        return report
    from production_checkpoint import digest
    checkpoint_root=Path("long_video_output/checkpoints").resolve()
    chapters=[]
    try:
        rows=json.loads((out/"completed-chapters.json").read_text(encoding="utf8"))
        for row in sorted(rows,key=lambda x:x["index"]):
            candidate=Path(row["path"]).resolve()
            if (candidate.is_relative_to(checkpoint_root) and candidate.is_file()
                    and digest(candidate)==row["sha256"]):
                chapters.append(candidate)
    except (OSError,ValueError,KeyError,TypeError):
        chapters=[]
    partial = out / "PARTIAL_REAL_CHAPTERS.mp4"
    if chapters:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="long-recovery-") as directory:
            playlist = Path(directory) / "chapters.txt"
            playlist.write_text("".join(
                "file '" + str(x.resolve()).replace("'", "'\\''") + "'\n"
                for x in chapters), encoding="utf8")
            subprocess.run([
                "ffmpeg", "-hide_banner", "-nostdin", "-y",
                "-loglevel", "error", "-f", "concat", "-safe", "0",
                "-i", str(playlist), "-c", "copy",
                "-movflags", "+faststart", str(partial)
            ], check=True, timeout=180)
        report["partial_real_mp4"] = str(partial)
        report["completed_real_chapters"] = len(chapters)
        print(f"[LONG PARTIAL REAL FOOTAGE] completed_chapters={len(chapters)} "
              "not a completed documentary")
    report.update(status="failed", mp4=None,
                  quality_reason="Full real-footage 10-minute documentary could "
                                 "not be verified; padded/repeated 2D was rejected",
                  original_error=report.get("error", ""))
    write_json(report_path, report)
    return report


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
