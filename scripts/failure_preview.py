"""Always provide an honest, playable preview alongside a FAILED video report.

Never turn a technical/factual failure into a successful final upload. If
genuine verified chapters were rendered, join those first. Otherwise preserve
a decodable rendered MP4, or show the available narrator audio over a labelled
preview card. If NOTHING was produced, a short, clearly labelled diagnostic
MP4 still lets the user see that the job ran instead of a ZIP with only JSON.

All media is local. No paid API, remote content, made-up stock, unsupported
narration or relaxation of the actual publication quality gates.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

PREVIEW_NAME = "PREVIEW_INCOMPLETE.mp4"


def _probe(path: Path) -> dict | None:
    if not path.is_file() or path.stat().st_size < 512:
        return None
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,width,height:format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=20)
        payload = json.loads(proc.stdout)
        streams = payload.get("streams", [])
        if not any(x.get("codec_type") == "video" for x in streams):
            return None
        if float(payload.get("format", {}).get("duration") or 0) < .25:
            return None
        return payload
    except (OSError, ValueError, subprocess.SubprocessError, TypeError):
        return None


def _audio_probe(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 1024:
        return False
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=20)
        return any(s.get("codec_type") == "audio"
                   for s in json.loads(proc.stdout).get("streams", []))
    except (OSError, ValueError, subprocess.SubprocessError, TypeError):
        return False


def _run(args, timeout=150):
    subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)


def _poster(path: Path, topic: str, stage: str, *, width: int, height: int):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (width, height), (17, 19, 24))
    draw = ImageDraw.Draw(img)
    # Warm charcoal—not a black video or fake documentary footage.
    for i in range(16):
        box_top = int(height * (0.08 + .048*i))
        draw.line((0, box_top, width, box_top),
                  fill=(24 + i//2, 26 + i//2, 30 + i//2), width=2)
    draw.rectangle((0, 0, int(width*.018), height), fill=(239, 159, 68))
    font_file = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    def font(size):
        try:
            return ImageFont.truetype(font_file, size)
        except OSError:
            return ImageFont.load_default()
    margin = max(26, width//16)
    draw.text((margin, int(height*.19)), "PREVIEW ONLY",
              font=font(max(23, width//22)), fill=(248, 179, 93))
    draw.text((margin, int(height*.31)), "VIDEO NOT COMPLETED",
              font=font(max(20, width//35)), fill=(251, 251, 249))
    normalized = " ".join(str(topic or "Untitled video").split())[:140]
    # Use a width-limited wrap; a title should never leave the visible crop.
    char_cap = max(15, int(width / max(14, width//28)))
    lines = textwrap.wrap(normalized, width=char_cap, max_lines=4,
                          placeholder="...")
    title_font = font(max(20, width//28))
    for i, line in enumerate(lines):
        draw.text((margin, int(height*.44) + i*int(width*.048)),
                  line, font=title_font, fill=(227, 230, 234))
    stage_text = "Stage: " + str(stage or "unknown").replace("_", " ")[:60]
    draw.text((margin, int(height*.83)), stage_text,
              font=font(max(15, width//44)), fill=(188, 193, 200))
    draw.text((margin, int(height*.89)), "Not ready for YouTube upload",
              font=font(max(15, width//45)), fill=(188, 193, 200))
    img.save(path)


def _card_video(out: Path, topic: str, stage: str, width: int, height: int,
                *, voice: Path | None = None):
    with tempfile.TemporaryDirectory(prefix="purffle-preview-") as temp:
        image = Path(temp) / "preview.png"
        _poster(image, topic, stage, width=width, height=height)
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
               "-loop", "1", "-framerate", "30", "-i", str(image)]
        if voice is not None and _audio_probe(voice):
            cmd.extend(["-i", str(voice)])
            seconds = "75"
            kind = "narration_with_preview_card"
        else:
            cmd.extend(["-f", "lavfi", "-i",
                        "anullsrc=channel_layout=stereo:sample_rate=44100"])
            seconds = "8"
            kind = "diagnostic_card_no_narration"
        cmd.extend(["-t", seconds, "-shortest",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "26", "-pix_fmt", "yuv420p",
                    "-r", "30", "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart", str(out)])
        _run(cmd, timeout=175)
        return kind


def _join_chapters(chapters: list[Path], out: Path) -> bool:
    """Preserve completed *rendered* chapters, not unlicensed source downloads."""
    if not chapters:
        return False
    with tempfile.TemporaryDirectory(prefix="purffle-partial-") as temp:
        playlist = Path(temp) / "chapters.txt"
        playlist.write_text(
            "\n".join("file '" + str(c.resolve()).replace("'", "'\\''") + "'"
                      for c in chapters) + "\n", encoding="utf-8")
        _run(["ffmpeg", "-hide_banner", "-nostdin", "-y",
              "-loglevel", "error", "-f", "concat", "-safe", "0",
              "-i", str(playlist), "-c", "copy",
              "-movflags", "+faststart", str(out)], timeout=150)
    return True


def make_failure_preview(*, output: Path, topic: str, stage: str,
                         size: tuple[int, int],
                         rendered_dir: Path | None = None,
                         long_chapters_dir: Path | None = None,
                         voice_dir: Path | None = None) -> dict:
    """Best-effort, no-API preview; never returns publication 'status=ok'.

    A crash, unavailable FFmpeg, invalid source or disk exhaustion can still
    prevent creating an MP4. Do not assert a file exists without ffprobe.
    """
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    kind, count = "", 0
    try:
        if long_chapters_dir is not None:
            chapters = sorted(
                path for path in Path(long_chapters_dir).glob("chapter-*.mp4")
                if _probe(path) is not None)
            if chapters:
                try:
                    _join_chapters(chapters, out)
                    kind, count = "completed_chapters_only", len(chapters)
                except (OSError, subprocess.SubprocessError):
                    out.unlink(missing_ok=True)
        if not kind and rendered_dir is not None:
            # Look only at *rendered outputs*, never raw source cache, because
            # arbitrary provider footage may not pass licensing/factual QA.
            valid = sorted(
                (p for p in Path(rendered_dir).rglob("*.mp4")
                 if p.resolve() != out.resolve() and _probe(p)),
                key=lambda p: p.stat().st_size, reverse=True)
            if valid:
                shutil.copyfile(valid[0], out)
                kind = "unverified_rendered_mp4"
        if not kind:
            voice = None
            if voice_dir is not None and Path(voice_dir).is_dir():
                files = sorted(Path(voice_dir).rglob("*.wav"))
                files += sorted(Path(voice_dir).rglob("*.mp3"))
                voice = next((p for p in files if _audio_probe(p)), None)
            kind = _card_video(out, topic, stage, *size, voice=voice)
        proof = _probe(out)
        if proof is None:
            raise RuntimeError("preview_not_decodable")
        return {
            "preview_status": "incomplete_not_publishable",
            "preview_mp4": str(out),
            "preview_kind": kind,
            "preview_chapter_count": count,
            "preview_duration": round(
                float(proof["format"]["duration"]), 2),
        }
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        out.unlink(missing_ok=True)
        return {
            "preview_status": "unavailable",
            "preview_error": type(exc).__name__,
        }
