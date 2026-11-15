"""Build a multi-shot, topic-related visual track from Wikimedia Commons."""
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

ALIASES = {"octopuses":"octopus","octopi":"octopus","oktopusse":"octopus","oktopus":"octopus","kraken":"octopus","himmel":"sky","erde":"earth","sonne":"sun","mond":"moon","katzen":"cat","hunde":"dog"}
STOP = set("why what how do does did is are the a an have has three and in of for to with their its can would if when where who was were about this that it they you your ist sind die der das und ein eine warum wie was haben hat den dem des von mit für".split())
UA = {"User-Agent":"PurffleVideoStudio/1.0 (GitHub educational video maker; contact via repository)"}

def relevant_background(topic: str, folder: Path):
    words = re.findall(r"[a-zA-ZäöüÄÖÜß]+", topic.lower())
    words = [ALIASES.get(w,w) for w in words if w not in STOP and len(w)>2]
    if not words:
        return None
    subject = words[0]
    params = urllib.parse.urlencode({
        "action":"query","generator":"search","gsrsearch":subject,
        "gsrnamespace":6,"gsrlimit":40,"prop":"imageinfo",
        "iiprop":"url|mime|extmetadata","iiurlwidth":960,"format":"json"
    })
    try:
        req=urllib.request.Request("https://commons.wikimedia.org/w/api.php?"+params,headers=UA)
        with urllib.request.urlopen(req,timeout=25) as response:
            pages=json.load(response).get("query",{}).get("pages",{})
        folder.mkdir(parents=True,exist_ok=True)
        clips=[]
        credits=[]
        # Prefer actual moving footage; still photos are a fallback.
        try:
            vparams=urllib.parse.urlencode({
                "action":"query","generator":"search","gsrsearch":subject+" filetype:video",
                "gsrnamespace":6,"gsrlimit":20,"prop":"imageinfo",
                "iiprop":"url|mime","format":"json"
            })
            with urllib.request.urlopen(urllib.request.Request(
                "https://commons.wikimedia.org/w/api.php?"+vparams,headers=UA),timeout=20) as response:
                vpages=json.load(response).get("query",{}).get("pages",{})
            for page in vpages.values():
                if len(clips)>=5: break
                info=(page.get("imageinfo") or [{}])[0]
                mime=info.get("mime","")
                if mime not in ("video/webm","video/ogg","video/mp4"): continue
                if subject not in page.get("title","").lower(): continue
                url=info.get("url")
                if not url: continue
                try:
                    # Stream at most 24 MiB per source; skip excessively large media.
                    req=urllib.request.Request(url,headers=UA)
                    with urllib.request.urlopen(req,timeout=25) as response:
                        if int(response.headers.get("Content-Length","0") or 0)>24*1024*1024: continue
                        raw=response.read(24*1024*1024+1)
                    if len(raw)>24*1024*1024 or len(raw)<20000: continue
                    source=folder/f"motion_{len(clips)+1:02d}.webm"
                    source.write_bytes(raw)
                    clip=folder/f"shot_{len(clips)+1:02d}.mp4"
                    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
                        "-stream_loop","-1","-i",str(source),"-t","9",
                        "-vf","scale=540:960:force_original_aspect_ratio=increase,crop=540:960,setsar=1,fps=12,format=yuv420p",
                        "-an","-c:v","libx264","-preset","ultrafast","-r","12",str(clip)],
                        check=True,timeout=65)
                    if clip.stat().st_size<15000: continue
                    clips.append(clip)
                    credits.append(page.get("title","")+" | "+url)
                    print("REAL MOTION SHOT",len(clips),page.get("title"),flush=True)
                except Exception as exc:
                    print("Skipping unusable video:",repr(exc),flush=True)
        except Exception as exc:
            print("Motion search unavailable, trying photos:",repr(exc),flush=True)

        # Strict video-only mode: never download or render still photographs.
        if not clips:
            print("No moving video clips found; skipping video (photos disabled)",flush=True)
            return None
        # At least five visual changes across 45 seconds, if five images were found.
        # Repeat moving clips only when fewer than five are available.
        sequence=(clips*5)[:5]
        manifest=folder/"shots.txt"
        manifest.write_text("".join("file '"+p.name+"'\n" for p in sequence),encoding="utf-8")
        (folder/"IMAGE_SOURCE.txt").write_text("\n".join(credits),encoding="utf-8")
        target=folder/"topic_background.mp4"
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","concat","-safe","0","-i",str(manifest),"-c","copy",str(target)],
            check=True,timeout=45)
        if target.stat().st_size<15000: return None
        print(f"VIDEO-ONLY BACKGROUND: {len(clips)} moving clips, 5 shots",flush=True)
        return str(target.resolve())
    except Exception as exc:
        print("Wikimedia multi-shot preparation failed:",repr(exc),flush=True)
        return None
