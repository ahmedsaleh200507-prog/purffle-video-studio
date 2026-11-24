"""Consolidate independent GitHub Actions video jobs into one downloadable artifact.

The collector runs even when a worker fails. Absence of an expected video
result is reported explicitly instead of silently reducing the requested count.
"""
from __future__ import annotations

import os
import json
from pathlib import Path

from batch import ROOT, parse_topic, write_json, write_consolidated_diagnostics
from youtube_metadata import attach_title_to_video, write_batch_titles


def aggregate(root: Path = ROOT) -> list[dict]:
    root = Path(root)
    out = root / "finished"
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for index in range(1, 11):
        raw = os.environ.get(f"INPUT_{index}", "").strip()
        if not raw:
            continue
        target = out / f"video_{index:02d}"
        path = target / "report.json"
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError("Worker report must contain an object")
        except (OSError, ValueError):
            result = {
                "index": index, "status": "failed", "topic": raw,
                "original_input": raw, "mp4": None,
                "failure_category": "unexpected",
                "error": "Worker did not provide a result (setup, test, runner or artifact failed)",
            }
        try:
            lang, topic = parse_topic(raw)
            result.setdefault("language", lang)
            result.setdefault("topic", topic)
        except ValueError:
            pass
        result["index"] = index
        # A report from the wrong slot or mismatched input is not accepted.
        if result.get("original_input", raw) != raw:
            result.update(status="failed", mp4=None,
                          failure_category="unexpected",
                          error="Worker report input does not match this requested topic")
        if result.get("status") in ("ok","review"):
            video = Path(result.get("mp4") or "")
            # Cross-runner paths saved by workers are absolute and point at a
            # DIFFERENT virtual machine. Locate the artifact's actual video.
            candidates = list(target.rglob("*.mp4"))
            if video.name:
                matching = [p for p in candidates if p.name == video.name]
                candidates = matching or candidates
            if len(candidates) != 1 or not candidates[0].is_file():
                result.update(status="failed", mp4=None, failure_category="unexpected",
                              error="Exactly one validated MP4 was expected in the downloaded worker artifact")
            else:
                result["mp4"] = str(candidates[0].resolve())
                try:
                    attach_title_to_video(result)
                except (OSError, ValueError, TypeError) as exc:
                    result["youtube_title_error"] = type(exc).__name__
        write_json(target / "report.json", result)
        results.append(result)
    write_json(root / "batch-results.json", results)
    # Diagnostic writer in batch.py normally writes to the repo root. The
    # collector uses the same ROOT in GitHub Actions; tests may monkeypatch it.
    import batch
    previous = batch.ROOT
    batch.ROOT = root
    try:
        write_consolidated_diagnostics(out, results)
    finally:
        batch.ROOT = previous
    write_batch_titles(root, results)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    ok = sum(r.get("status") == "ok" for r in results)
    review = sum(r.get("status") == "review" for r in results)
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write(f"## Purffle — {ok} verified, {review} review MP4s, {len(results)-ok-review} failed\n\n")
            for row in results:
                index, status = row["index"], row.get("status", "failed")
                file.write(f"- Video {index:02d}: **{status}**")
                if status != "ok":
                    file.write(" — " + str(row.get("error", "unknown failure")))
                file.write("\n")
    print(f"[BATCH COLLECTED] requested={len(results)} succeeded={ok} failed={len(results)-ok}",
          flush=True)
    return results


if __name__ == "__main__":
    aggregate()
