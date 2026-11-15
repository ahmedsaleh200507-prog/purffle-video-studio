"""Run up to ten independent Purffle video jobs on GitHub Actions."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

OUT = Path("finished")
OUT.mkdir(exist_ok=True)
results = []
if not os.environ.get("GROQ_API_KEY") or not os.environ.get("PIXABAY_API_KEY"):
    print("Missing GROQ_API_KEY or PIXABAY_API_KEY in repository Actions secrets.", flush=True)
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
        "--no-music", "--no-sfx", "--no-emoji",
    ]
    print(f"\n=== VIDEO {index}/10 [{lang}] {topic} ===", flush=True)
    started = time.monotonic()
    status = "ok"
    try:
        # A stalled video must not block the entire batch.
        subprocess.run(cmd, check=True, timeout=720)
    except subprocess.TimeoutExpired:
        status = "timeout"
        print(f"Video {index} timed out after 12 minutes", flush=True)
    except subprocess.CalledProcessError as exc:
        status = f"failed (exit {exc.returncode})"
        print(f"Video {index} failed: {exc}", flush=True)
    new_files = [p for p in work.rglob("*.mp4") if p.resolve() not in before and p.stat().st_size > 1000]
    if new_files:
        for n, source in enumerate(sorted(new_files), 1):
            shutil.copy2(source, target / f"video_{index:02d}_{lang}_{n}.mp4")
        status = "ok"
    else:
        status = "no_mp4" if status == "ok" else status
    results.append({"index": index, "language": lang, "topic": topic, "status": status,
                    "seconds": round(time.monotonic() - started, 1), "files": len(new_files)})
    Path("batch-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== VIDEO {index} DONE: {status} ===", flush=True)

print("\nFinished:", json.dumps(results, ensure_ascii=False), flush=True)
if not results:
    print("No video topics were supplied.", flush=True)
    sys.exit(1)
if not any(r["status"] == "ok" for r in results):
    sys.exit(1)
