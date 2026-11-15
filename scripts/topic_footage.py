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
        for page in sorted(pages.values(),key=lambda p:(subject not in p.get("title","").lower(),p.get("title",""))):
            if len(clips)>=5: break
            title=page.get("title","").lower()
            if subject not in title: continue
            info=(page.get("imageinfo") or [{}])[0]
            mime=info.get("mime")
            if mime not in ("image/jpeg","image/png","image/webp"): continue
            url=info.get("thumburl") or info.get("url")
            if not url: continue
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=20) as response:
                    data=response.read(8*1024*1024+1)
                if not 10000<len(data)<8*1024*1024: continue
                suffix={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}[mime]
                image=folder/f"shot_{len(clips)+1:02d}{suffix}"
                image.write_bytes(data)
                clip=folder/f"shot_{len(clips)+1:02d}.mp4"
                # Each 9-second shot is independently encoded for reliable concatenation.
                subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
                    "-loop","1","-framerate","12","-i",str(image),"-t","9",
                    "-vf","scale=540:960:force_original_aspect_ratio=increase,crop=540:960,setsar=1,format=yuv420p",
                    "-an","-c:v","libx264","-preset","ultrafast","-r","12",str(clip)],
                    check=True,timeout=45)
                if clip.stat().st_size<10000: continue
                clips.append(clip)
                credits.append(page.get("title","")+" | "+info.get("descriptionurl",url))
                print("VISUAL SHOT",len(clips),page.get("title"),flush=True)
            except Exception as exc:
                print("Skipping unusable Wikimedia image:",repr(exc),flush=True)
        if not clips:
            print("No usable subject visuals",flush=True)
            return None
        # At least five visual changes across 45 seconds, if five images were found.
        # Repeat available shots only when Commons provides fewer than five.
        sequence=(clips*5)[:5]
        manifest=folder/"shots.txt"
        manifest.write_text("".join("file '"+p.name+"'\n" for p in sequence),encoding="utf-8")
        (folder/"IMAGE_SOURCE.txt").write_text("\n".join(credits),encoding="utf-8")
        target=folder/"topic_background.mp4"
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","concat","-safe","0","-i",str(manifest),"-c","copy",str(target)],
            check=True,timeout=45)
        if target.stat().st_size<15000: return None
        print(f"MULTI-SHOT BACKGROUND: {len(clips)} unique images, 5 shots",flush=True)
        return str(target.resolve())
    except Exception as exc:
        print("Wikimedia multi-shot preparation failed:",repr(exc),flush=True)
        return None
