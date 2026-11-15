"""Run up to ten independent Purffle video jobs on GitHub Actions."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from topic_footage import relevant_background
from visual_quality import has_visual_detail

OUT = Path("finished")
OUT.mkdir(exist_ok=True)
results = []
if not os.environ.get("GROQ_API_KEY"):
    print("Missing GROQ_API_KEY in repository Actions secrets.", flush=True)
    sys.exit(2)

for index in range(1, 11):
    raw = os.environ.get(f"INPUT_{index}", "").strip()
    if not raw:
        continue
    if "|" in raw and raw.split("|", 1)[0].strip().lower() in ("de", "en"):
        lang, topic = raw.split("|", 1)
        lang = lang.strip().lower()
        topic = topic.strip()
    else:
        lang, topic = "en", raw
    if not topic:
        continue
    target = OUT / f"video_{index:02d}_{lang}"
    target.mkdir(exist_ok=True)
    work = Path("output_videos")
    work.mkdir(exist_ok=True)
    before = {p.resolve() for p in work.rglob("*.mp4")}
    cmd = [
        sys.executable, "-m", "purffle_shorts", "make",
        "--topic", topic, "--style", "facts", "--lang", lang,
        "--duration", "25", "--caption-style", "bold",
        "--resolution", "540x960", "--fps", "24",
        "--visuals", "pixabay", "--no-review", "--no-upload",
        "--no-music",
    ]
    # Use the original Purffle per-scene search queries with the existing Pixabay key.
    # Only fall back to custom animated footage if no stock API is configured.
    background = None
    if os.environ.get("PIXABAY_API_KEY"):
        print("UPSTREAM SCENE VISUALS: Pixabay per-scene search enabled",flush=True)
    elif os.environ.get("PEXELS_API_KEY"):
        cmd[cmd.index("--visuals")+1] = "pexels"
        print("UPSTREAM SCENE VISUALS: Pexels per-scene search enabled",flush=True)
    else:
        try:
            background = relevant_background(topic, Path("media_cache") / f"video_{index:02d}")
        except Exception as exc:
            print("VISUAL PREPARATION ERROR:",repr(exc),flush=True)
        if background:
            cmd += ["--background", background, "--layout", "full"]
        else:
            print(f"Video {index}: unable to prepare moving visuals",flush=True)
            results.append({"index":index,"language":lang,"topic":topic,"status":"no_relevant_visual","seconds":0,"files":0})
            continue
    print(f"\n=== VIDEO {index}/10 [{lang}] {topic} ===", flush=True)
    started = time.monotonic()
    status = "ok"
    try:
        # A stalled video must not block the entire batch.
        log_path = target / "purffle.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, text=True)
            try:
                process.wait(timeout=420)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise
            if process.returncode:
                print("PURFFLE FAILED, last 35 log lines:", flush=True)
                print("\n".join(log_path.read_text(errors="replace").splitlines()[-35:]), flush=True)
                raise subprocess.CalledProcessError(process.returncode, cmd)
    except subprocess.TimeoutExpired:
        status = "timeout"
        print(f"Video {index} timed out after 7 minutes", flush=True)
    except subprocess.CalledProcessError as exc:
        status = f"failed (exit {exc.returncode})"
        print(f"Video {index} failed: {exc}", flush=True)
    new_files = [p for p in work.rglob("*.mp4") if p.resolve() not in before and p.stat().st_size > 1000]
    if new_files:
        for n, source in enumerate(sorted(new_files), 1):
            destination = target / f"video_{index:02d}_{lang}_{n}.mp4"
            # Keep already-good footage: color-keying can destroy actual images.
            if has_visual_detail(source):
                shutil.copy2(source, destination)
                print("Original MP4 contains real footage; no overlay needed", flush=True)
            elif background:
                print("Blank frame detected; repairing with verified topic footage", flush=True)
                try:
                    probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(source)],
                        capture_output=True, text=True, timeout=12, check=True)
                    w, h = (int(x) for x in probe.stdout.strip().split(",")[:2])
                    filtergraph = (
                        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                        f"crop={w}:{h},setsar=1[bg];"
                        f"[1:v]format=rgba,colorkey=0x0b263d:0.23:0.08[fg];"
                        f"[bg][fg]overlay=shortest=1:format=auto,format=yuv420p[out]"
                    )
                    subprocess.run([
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-stream_loop", "-1", "-i", background, "-i", str(source),
                        "-filter_complex", filtergraph, "-map", "[out]", "-map", "1:a?",
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                        "-c:a", "copy", "-t", "35", "-shortest", str(destination)
                    ], check=True, timeout=100)
                    if not destination.exists() or destination.stat().st_size < 15000 or not has_visual_detail(destination):
                        raise RuntimeError("Visual repair failed quality check")
                except Exception as exc:
                    print("Visual repair failed:", repr(exc), flush=True)
                    destination.unlink(missing_ok=True)
                    status = "visual_overlay_failed"
            else:
                print("Blank/low-detail output rejected; no valid visual fallback",flush=True)
                status = "visual_quality_failed"
        if any(target.glob("*.mp4")):
            status = "ok"
        if status == "ok" and not any(target.glob("*.mp4")):
            status = "visual_overlay_failed"
    else:
        status = "no_mp4" if status == "ok" else status
    results.append({"index": index, "language": lang, "topic": topic, "status": status,
                    "seconds": round(time.monotonic() - started, 1), "files": len(list(target.glob("*.mp4")))})
    Path("batch-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== VIDEO {index} DONE: {status} ===", flush=True)

print("\nFinished:", json.dumps(results, ensure_ascii=False), flush=True)
if not results:
    print("No video topics were supplied.", flush=True)
    sys.exit(1)
if not any(r["status"] == "ok" for r in results):
    sys.exit(1)
