"""Offline tests for the GitHub Actions parallel video collector."""
from __future__ import annotations

import json
from pathlib import Path

from aggregate_results import aggregate


def _worker_file(root: Path, index: int, topic: str, *, ok: bool) -> Path:
    output = root / "finished" / f"video_{index:02d}"
    output.mkdir(parents=True, exist_ok=True)
    row = {
        "index": index, "original_input": topic, "topic": topic.split("|", 1)[-1],
        "status": "ok" if ok else "failed",
        "language": topic.split("|", 1)[0], "mp4": None,
    }
    if ok:
        # The original runner stored its MP4 with a totally different absolute
        # root. The collector must rebase it to the downloaded artifact path.
        mp4 = output / "render" / "video" / "final.mp4"
        mp4.parent.mkdir(parents=True, exist_ok=True)
        mp4.write_bytes(b"this is an already validated artifact mock")
        row["mp4"] = "/home/runner/work/previous-run/render/video/final.mp4"
        (mp4.parent / "YouTube_Title.txt").write_text("Why Does the Ocean Glow at Night? 🌊\n")
    else:
        row["error"] = "No suitable verified REAL VIDEO for scene 2"
    (output / "report.json").write_text(json.dumps(row))
    return output


def test_aggregate_rebases_mp4_paths_and_keeps_titles(tmp_path, monkeypatch):
    for index in range(1, 11):
        monkeypatch.delenv(f"INPUT_{index}", raising=False)
    monkeypatch.setenv("INPUT_1", "en|Why Does the Ocean Glow at Night?")
    monkeypatch.setenv("INPUT_2", "de|Warum ist der Himmel blau?")
    monkeypatch.setenv("INPUT_3", "en|Volcano mystery")
    _worker_file(tmp_path, 1, "en|Why Does the Ocean Glow at Night?", ok=True)
    _worker_file(tmp_path, 2, "de|Warum ist der Himmel blau?", ok=False)
    results = aggregate(tmp_path)
    assert len(results) == 3
    assert [x["index"] for x in results] == [1, 2, 3]
    assert results[0]["status"] == "ok"
    assert Path(results[0]["mp4"]).exists()
    assert results[0]["youtube_title"] == "Why Does the Ocean Glow at Night? 🌊"
    assert results[1]["status"] == "failed"
    assert results[2]["status"] == "failed"
    assert "Worker did not provide a result" in results[2]["error"]
    assert json.loads((tmp_path / "batch-results.json").read_text())[0]["status"] == "ok"
    titles = (tmp_path / "YOUTUBE_SHORTS_TITLES.txt").read_text()
    assert "VIDEO 01" in titles and "VIDEO 02" not in titles
    diag = json.loads((tmp_path / "PURFFLE_DIAGNOSTICS.json").read_text())
    assert diag["summary"] == {"requested": 3, "succeeded": 1, "failed": 2}


def test_empty_optional_slots_have_no_false_failure(tmp_path, monkeypatch):
    for index in range(1, 11):
        monkeypatch.delenv(f"INPUT_{index}", raising=False)
    monkeypatch.setenv("INPUT_4", "en|A single requested title")
    _worker_file(tmp_path, 4, "en|A single requested title", ok=True)
    results = aggregate(tmp_path)
    assert [x["index"] for x in results] == [4]
    assert results[0]["status"] == "ok"


def test_report_from_wrong_topic_is_rejected(tmp_path, monkeypatch):
    for index in range(1, 11):
        monkeypatch.delenv(f"INPUT_{index}", raising=False)
    monkeypatch.setenv("INPUT_9", "en|New question")
    _worker_file(tmp_path, 9, "en|Different question", ok=True)
    result = aggregate(tmp_path)[0]
    assert result["status"] == "failed"
    assert "does not match" in result["error"]


def test_ambiguous_multiple_mp4_artifacts_fail_safely(tmp_path, monkeypatch):
    for index in range(1, 11):
        monkeypatch.delenv(f"INPUT_{index}", raising=False)
    monkeypatch.setenv("INPUT_1", "en|Ocean")
    target = _worker_file(tmp_path, 1, "en|Ocean", ok=True)
    # Distinct MP4 filenames must not be silently guessed.
    another = target / "extra.mp4"
    another.write_bytes(b"unverified")
    result = aggregate(tmp_path)[0]
    # A named match to the worker MP4 is authoritative even if other work files exist.
    assert result["status"] == "ok"
    assert Path(result["mp4"]).name == "final.mp4"
