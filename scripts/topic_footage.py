"""Build a multi-shot, topic-related visual track from Wikimedia Commons."""
import json
import os
import time
import urllib.error
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
    try:
        folder.mkdir(parents=True,exist_ok=True)
        clips=[]
        credits=[]
        # Video only: reject clips without detectable frame-to-frame movement.
        try:
            vparams=urllib.parse.urlencode({
                "action":"query","generator":"search","gsrsearch":subject+" filetype:video",
                "gsrnamespace":6,"gsrlimit":40,"prop":"imageinfo",
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
                    cache=Path("media_cache")/"downloads"
                    cache.mkdir(parents=True,exist_ok=True)
                    import hashlib
                    key=hashlib.sha256(url.encode()).hexdigest()[:24]
                    cached=cache/(key+".bin")
                    if cached.exists():
                        raw=cached.read_bytes()
                    else:
                        raw=None
                        for attempt in range(3):
                            try:
                                with urllib.request.urlopen(req,timeout=35) as response:
                                    if int(response.headers.get("Content-Length","0") or 0)>24*1024*1024: break
                                    raw=response.read(24*1024*1024+1)
                                break
                            except urllib.error.HTTPError as e:
                                if e.code != 429: raise
                                delay=min(25, 5*(attempt+1))
                                print(f"Rate limit 429; waiting {delay}s",flush=True)
                                time.sleep(delay)
                        if raw is None: continue
                        if 20000<len(raw)<24*1024*1024: cached.write_bytes(raw)
                        time.sleep(1.5)
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
                    probe=subprocess.run(["ffmpeg","-v","error","-i",str(clip),
                        "-vf","fps=1,scale=32:32,format=gray","-frames:v","7",
                        "-f","rawvideo","-"],capture_output=True,timeout=20,check=True)
                    frames=[probe.stdout[i:i+1024] for i in range(0,len(probe.stdout),1024)]
                    if len(frames)<3: continue
                    changes=[sum(abs(a-b) for a,b in zip(x,y))/1024
                             for x,y in zip(frames,frames[1:])]
                    if max(changes)<1.5:
                        print("Rejected static or near-static clip:",page.get("title"),flush=True)
                        continue
                    clips.append(clip)
                    credits.append(page.get("title","")+" | "+url)
                    print("REAL MOTION SHOT",len(clips),page.get("title"),flush=True)
                except Exception as exc:
                    print("Skipping unusable video:",repr(exc),flush=True)
        except Exception as exc:
            print("Motion search unavailable:",repr(exc),flush=True)

        # Strict video-only mode: never download or render still photographs.
        if not clips:
            print("No downloadable moving footage; creating original 2D motion graphic fallback",flush=True)
            # Procedural moving background, not a still photograph or empty color card.
            # FFmpeg's moving plasma pattern ensures continuous changing pixels.
            fallback=folder/"procedural_motion.mp4"
            subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
                "-f","lavfi","-i","cellauto=s=540x960:r=12:rule=110:random_fill_ratio=0.35",
                "-t","9","-vf","format=yuv420p",
                "-an","-c:v","libx264","-preset","ultrafast",str(fallback)],
                check=True,timeout=65)
            if not fallback.exists() or fallback.stat().st_size<15000:
                raise RuntimeError("Moving fallback generation failed")
            clips.append(fallback)
            credits.append("Original procedurally animated 2D motion background")
        if len(clips)<5:
            print(f"Only {len(clips)} distinct moving clips; looping available motion instead of cancelling",flush=True)
        # Keep continuous motion for narration and any offset; never use blank fillers.
        sequence=(clips*15)[:15]
        manifest=folder/"shots.txt"
        manifest.write_text("".join("file '"+p.name+"'\n" for p in sequence),encoding="utf-8")
        (folder/"IMAGE_SOURCE.txt").write_text("\n".join(credits),encoding="utf-8")
        target=folder/"topic_background.mp4"
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","concat","-safe","0","-i",str(manifest),"-c","copy",str(target)],
            check=True,timeout=45)
        if target.stat().st_size<15000: return None
        print(f"VIDEO-ONLY BACKGROUND: {len(clips)} moving sources, 15 shots (135s)",flush=True)
        return str(target.resolve())
    except Exception as exc:
        print("Wikimedia multi-shot preparation failed:",repr(exc),flush=True)
        return None
