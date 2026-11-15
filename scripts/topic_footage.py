"""Get subject-related imagery from Wikimedia Commons, independent of Pixabay keys."""
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

ALIASES = {"octopuses":"octopus","octopi":"octopus","oktopusse":"octopus","oktopus":"octopus","kraken":"octopus","himmel":"sky","erde":"earth","sonne":"sun","mond":"moon","katzen":"cat","hunde":"dog"}
STOP = set("why what how do does did is are the a an have has three and in of for to with their its can would if when where who was were about this that it they you your ist sind die der das und ein eine warum wie was haben hat den dem des von mit für".split())

def relevant_background(topic: str, folder: Path):
    words = re.findall(r"[a-zA-ZäöüÄÖÜß]+", topic.lower())
    words = [ALIASES.get(w,w) for w in words if w not in STOP and len(w)>2]
    if not words:
        print("No meaningful topic keywords", flush=True)
        return None
    subject = words[0]
    # Commons is independent of Pixabay's API 403 error.
    params = urllib.parse.urlencode({
        "action":"query","generator":"search","gsrsearch":subject,
        "gsrnamespace":6,"gsrlimit":12,"prop":"imageinfo",
        "iiprop":"url|mime|extmetadata","iiurlwidth":960,"format":"json"
    })
    try:
        req=urllib.request.Request("https://commons.wikimedia.org/w/api.php?"+params,
            headers={"User-Agent":"PurffleVideoStudio/1.0 (GitHub educational video maker; contact via repository)"})
        with urllib.request.urlopen(req,timeout=20) as response:
            pages=json.load(response).get("query",{}).get("pages",{})
        for page in sorted(pages.values(), key=lambda p: (subject not in p.get("title", "").lower(), p.get("title", ""))):
            title=page.get("title","").lower()
            if subject not in title:
                continue
            info=(page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in ("image/jpeg","image/png","image/webp"):
                continue
            url=info.get("thumburl") or info.get("url")
            if not url: continue
            folder.mkdir(parents=True,exist_ok=True)
            req=urllib.request.Request(url,headers={"User-Agent":"PurffleVideoStudio/1.0 (GitHub educational video maker)"})
            with urllib.request.urlopen(req,timeout=20) as response:
                data=response.read(9*1024*1024)
            if len(data)>8*1024*1024 or len(data)<10000: continue
            suffix={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}[info["mime"]]
            image=folder/("topic_image"+suffix)
            image.write_bytes(data)
            (folder/"IMAGE_SOURCE.txt").write_text(info.get("descriptionurl",url)+"\n"+str(info.get("extmetadata",{})),encoding="utf-8")
            target=folder/"topic_background.mp4"
            subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-loop","1",
                "-framerate","12","-i",str(image),"-t","40",
                "-vf","scale=540:960:force_original_aspect_ratio=increase,crop=540:960,format=yuv420p",
                "-c:v","libx264","-preset","ultrafast","-r","12",str(target)],check=True,timeout=80)
            if target.exists() and target.stat().st_size>10000:
                print("VERIFIED SUBJECT IMAGE:",page["title"],flush=True)
                return str(target.resolve())
    except Exception as exc:
        print("Wikimedia search failed:",repr(exc),flush=True)
    print("NO SUBJECT IMAGE AVAILABLE - refusing blank video",flush=True)
    return None
