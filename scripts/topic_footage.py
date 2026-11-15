"""Find a genuinely topic-related Pixabay video; never substitute generic scenery."""
import os
import re
import urllib.parse
import urllib.request
import json
from pathlib import Path
import subprocess

STOP = {"why","what","how","do","does","did","is","are","the","a","an","have","has","three","and","in","of","for","to","with","their","its","can","would","if","when","where","who","was","were","about","this","that","it","they","you","your","why","ist","sind","die","der","das","und","ein","eine","warum","wie","was","haben","hat","den","dem","des","von","mit","für"}
ALIASES = {"octopuses":"octopus","octopi":"octopus","kraken":"octopus","oktopusse":"octopus","oktopus":"octopus","herzen":"heart","himmel":"sky","blau":"blue","erde":"earth","sonne":"sun","mond":"moon","katzen":"cat","hunde":"dog"}
def relevant_background(topic: str, folder: Path):
    key = os.environ.get("PIXABAY_API_KEY","")
    if not key: return None
    words = re.findall(r"[a-zA-ZäöüÄÖÜß]+", topic.lower())
    words = [ALIASES.get(w,w) for w in words if w not in STOP and len(w)>2]
    if not words: return None
    # Strongest subject noun is usually the first content word.
    subject = words[0]
    query = urllib.parse.urlencode({"key":key,"q":subject,"per_page":10,"safesearch":"true"})
    try:
        req = urllib.request.Request("https://pixabay.com/api/videos/?"+query,headers={"User-Agent":"PurffleVideoStudio/1.0"})
        with urllib.request.urlopen(req,timeout=12) as resp:
            hits=json.load(resp).get("hits",[])
        for hit in hits:
            tags=set(re.findall(r"[a-z]+",hit.get("tags","").lower()))
            # Require subject in the tags: no unrelated forest/waterfall fallback.
            if subject not in tags and not any(subject in t or t in subject for t in tags if len(t)>3):
                continue
            videos=hit.get("videos",{})
            v=videos.get("medium") or videos.get("small") or videos.get("large") or {}
            url=v.get("url")
            if not url: continue
            folder.mkdir(parents=True,exist_ok=True)
            target=folder/"topic_background.mp4"
            with urllib.request.urlopen(url,timeout=25) as src, target.open("wb") as out:
                total=0
                while True:
                    chunk=src.read(1024*1024)
                    if not chunk: break
                    total+=len(chunk)
                    if total>35*1024*1024: raise ValueError("Background too large")
                    out.write(chunk)
            if target.stat().st_size>10000:
                print("Verified topic footage:",subject,hit.get("tags",""),flush=True)
                return str(target.resolve())
    except Exception as exc:
        print("Topic video search unavailable:", type(exc).__name__, flush=True)
    # Fallback: a subject-matched still photo animated into a lightweight MP4.
    # Do not fall back to generic scenery or unbounded searches.
    try:
        query = urllib.parse.urlencode({"key": key, "q": subject, "per_page": 10, "image_type": "photo", "safesearch": "true"})
        with urllib.request.urlopen("https://pixabay.com/api/?" + query, timeout=12) as response:
            hits = json.load(response).get("hits", [])
        for hit in hits:
            tags = set(re.findall(r"[a-z]+", hit.get("tags", "").lower()))
            if not any(subject == tag or subject in tag for tag in tags):
                continue
            url = hit.get("largeImageURL") or hit.get("webformatURL")
            if not url:
                continue
            folder.mkdir(parents=True, exist_ok=True)
            photo = folder / "topic_photo.jpg"
            with urllib.request.urlopen(url, timeout=15) as response:
                data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                continue
            photo.write_bytes(data)
            target = folder / "topic_background.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-loop", "1", "-framerate", "12", "-i", str(photo),
                "-t", "40", "-vf", "scale=540:960:force_original_aspect_ratio=increase,crop=540:960,format=yuv420p",
                "-c:v", "libx264", "-preset", "ultrafast", "-r", "12", str(target)
            ], check=True, timeout=60)
            if target.exists() and target.stat().st_size > 10000:
                print("Verified topic PHOTO fallback:", subject, hit.get("tags", ""), flush=True)
                return str(target.resolve())
    except Exception as exc:
        print("Topic photo fallback failed:", repr(exc), flush=True)
    # Last resort: topic-specific text card. It is honest, not random scenery.
    try:
        folder.mkdir(parents=True, exist_ok=True)
        title = re.sub(r"[^\w\s?!.,-]", "", topic, flags=re.UNICODE)[:100]
        words = title.split()
        lines = []
        while words:
            lines.append(" ".join(words[:4]))
            words = words[4:]
        (folder / "title.txt").write_text("\n".join(lines[:6]), encoding="utf-8")
        target = folder / "topic_background.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=0x0a243c:s=540x960:r=12",
            "-t", "40", "-vf",
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile="
            + str((folder / "title.txt").resolve())
            + ":fontcolor=white:fontsize=34:line_spacing=16:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(target)
        ], check=True, timeout=65)
        print("Using topic-specific title card (no unrelated scenery)", flush=True)
        return str(target.resolve())
    except Exception as exc:
        print("Topic card creation failed:", repr(exc), flush=True)
    return None
