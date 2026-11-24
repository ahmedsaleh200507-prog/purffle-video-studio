"""Completion-first documentary recovery: licensed stills, then clearly marked
original chapter illustrations. Never classify these as verified real footage."""
import html
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

UA = "PurffleDocumentary/1.0 (https://github.com/ahmedsaleh200507-prog/purffle-video-studio)"

def request(url, params):
    req = urllib.request.Request(url+"?"+urllib.parse.urlencode(params),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)

def clean(value):
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or ""))).strip()

def commons(query):
    data = request("https://commons.wikimedia.org/w/api.php", {
        "action":"query","generator":"search","gsrsearch":query+" filetype:bitmap",
        "gsrnamespace":6,"gsrlimit":12,"prop":"imageinfo",
        "iiprop":"url|size|mime|extmetadata","iiurlwidth":1600,"format":"json",
    })
    for page in data.get("query",{}).get("pages",{}).values():
        for info in page.get("imageinfo",[]):
            m=info.get("extmetadata",{})
            def meta(k): return clean(m.get(k,{}).get("value"))
            from video_sources import LicenseValidator
            label=meta("LicenseShortName")
            license_url=meta("LicenseUrl")
            license_id=LicenseValidator.identify(license_url)
            if not license_id and not license_url:
                if label.casefold() in ("cc0","cc0 1.0"):
                    license_id="CC0-1.0"
                    license_url="https://creativecommons.org/publicdomain/zero/1.0/"
                elif label.casefold()=="public domain":
                    license_id="PDM-1.0"
                    license_url="https://creativecommons.org/publicdomain/mark/1.0/"
            # No mandatory attribution, ShareAlike or non-commercial terms.
            if license_id not in ("CC0-1.0","PDM-1.0"):
                continue
            if not LicenseValidator.validate({"id":license_id,"url":license_url,
                    "source_page":info.get("descriptionurl","")}):
                continue
            if re.search(r"copyrighted|all rights reserved|non.commercial|permission required",
                    meta("Restrictions")+" "+meta("UsageTerms"),re.I):
                continue
            if info.get("mime") not in ("image/jpeg","image/png","image/webp"):
                continue
            if min(info.get("width",0),info.get("height",0))<720:
                continue
            url=info.get("thumburl") or info.get("url")
            if urllib.parse.urlparse(url or "").hostname!="upload.wikimedia.org":
                continue
            yield url, {"source":"wikimedia-photo","id":page["pageid"],
                "creator":meta("Artist") or meta("Credit") or "See original file",
                "license":license_id,"license_url":license_url,"attribution_required":False,
                "source_page":info.get("descriptionurl"),"query":query,
                "metadata_text":page.get("title","")+" "+meta("ImageDescription"),
                "visual_check":"licensed_still_search_match",
                "visual_role":"illustrative_photo","media_type":"photo"}

def pixabay(query):
    key=os.environ.get("PIXABAY_API_KEY")
    if not key: return
    data=request("https://pixabay.com/api/",{"key":key,"q":query,
        "image_type":"photo","safesearch":"true","per_page":12,
        "min_width":1280,"min_height":720})
    for hit in data.get("hits",[]):
        url=hit.get("largeImageURL")
        if urllib.parse.urlparse(url or "").hostname not in ("pixabay.com","cdn.pixabay.com"):
            continue
        yield url, {"source":"pixabay-photo","id":hit["id"],
            "creator":hit.get("user",""),"license":"Pixabay Content License",
            "license_url":"https://pixabay.com/service/license-summary/","attribution_required":False,
            "source_page":hit.get("pageURL"),"query":query,
            "metadata_text":hit.get("tags",""),
            "visual_check":"licensed_still_search_match",
            "visual_role":"illustrative_photo","media_type":"photo"}

def download_photo(url, dest, size=(1920,1080)):
    from PIL import Image, ImageOps
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=20) as response:
        data=response.read(20*1024*1024+1)
    if len(data)>20*1024*1024: raise ValueError("photo too large")
    import io
    with Image.open(io.BytesIO(data)) as im:
        im=ImageOps.exif_transpose(im).convert("RGB")
        if min(im.size)<720: raise ValueError("photo below HD")
        # Fit without stretching and reject nearly blank assets.
        from PIL import ImageStat
        if max(ImageStat.Stat(im.resize((64,64))).stddev)<8:
            raise ValueError("nearly blank photo")
        im=ImageOps.fit(im,size,method=Image.Resampling.LANCZOS)
        im.save(dest,quality=92)
    return dest

def illustrations(chapter, index, directory):
    """Last resort only: factual chapter cards using the actual spoken script.
    Explicitly marked as illustrations, never represented as real footage."""
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
    font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    title_font=ImageFont.truetype(bold,64)
    body_font=ImageFont.truetype(font,48)
    label_font=ImageFont.truetype(bold,24)
    sentences=re.split(r"(?<=[.!?])\s+",chapter.get("narration",""))
    sentences=[s for s in sentences if s.strip()]
    count=min(4,max(1,len(sentences)))
    for i in range(count):
        im=Image.new("RGB",(1920,1080),(20,38,55))
        draw=ImageDraw.Draw(im)
        for y in range(1080):
            draw.line((0,y,1920,y),fill=(20+y//45,38+y//35,55+y//30))
        draw.rounded_rectangle((110,120,1810,960),radius=36,fill=(33,58,77),
                               outline=(95,169,180),width=3)
        draw.text((170,170),"ILLUSTRATION / VERANSCHAULICHUNG",font=label_font,fill=(160,220,220))
        title="\n".join(textwrap.wrap(chapter.get("title",""),width=40))
        draw.multiline_text((170,245),title,font=title_font,fill="white",spacing=10)
        start=i*len(sentences)//count
        end=(i+1)*len(sentences)//count
        excerpt=" ".join(sentences[start:end])
        excerpt="\n".join(textwrap.wrap(excerpt,width=62)[:7])
        draw.multiline_text((170,460),excerpt,font=body_font,fill=(230,239,242),spacing=12)
        draw.text((170,875),f"{index:02d} / 14",font=label_font,fill=(160,220,220))
        path=directory/f"illustration-{i}.jpg"
        im.save(path,quality=94)
        yield path,{"source":"original-chapter-illustration","id":f"{index}-{i}",
                    "media_type":"illustration","visual_role":"last_resort",
                    "visual_check":"not_real_footage"}

def verify_photo(path,subject,query,matcher):
    from PIL import Image
    with Image.open(path) as im:
        frame=im.convert("RGB")
    captions=[f"A real photograph showing {query}.",f"A real photograph showing {subject}.",
              "An unrelated landscape or empty background.", "A drawing or illustration.",
              "A text slide or screenshot.", "An unrelated indoor scene."]
    values=matcher._similarities([frame],captions)[0]
    positive=max(values[:2])
    margin=positive-max(values[2:])
    if positive<.23 or values[1]<.20 or margin<.008:
        raise ValueError("Photo subject not verified in actual cropped image")
    return {"visual_check":"local_clip_photo_screening","visual_score":round(positive,4),
            "visual_margin":round(margin,4),"visual_role":"illustrative_photo"}

def stills(chapter,index,work,seen,*,size=(1920,1080),limit=4,require_verified=False,matcher=None):
    directory=work/f"stills-{index:02d}"
    directory.mkdir(parents=True,exist_ok=True)
    queries=list(dict.fromkeys(q for q in (chapter.get("visual_search_query"),
        chapter.get("visual_subject")) if q))
    from geography_policy import scene_requirement,scoped_queries,require_geography
    from era_policy import scene_era,footage_allowed
    required_regions=(chapter["required_regions"] if "required_regions" in chapter
                      else scene_requirement(chapter,chapter.get("topic","")))
    queries=scoped_queries(queries,required_regions)
    era=scene_era(chapter)
    selected=[]
    require_verified=require_verified or os.environ.get("PURFFLE_VERIFIED_PHOTO_ONLY")=="1"
    if require_verified and matcher is None:
        from media_validation import SceneMatcher
        matcher=SceneMatcher(threshold=.23)
    subject=chapter.get("visual_subject","").casefold()
    terms=[x for x in re.findall(r"\w+",subject) if len(x)>=3]
    for query in queries:
        for provider in (commons,pixabay):
            try:
                for url,credit in provider(query):
                    if len(selected)>=limit: return selected
                    key=(credit["source"],str(credit["id"]))
                    if key in seen: continue
                    if terms and not any(t in credit.get("metadata_text","").casefold() for t in terms):
                        continue
                    path=directory/f"photo-{len(selected)}.jpg"
                    try:
                        credit["geography_evidence"]=require_geography(required_regions,credit.get("metadata_text",""))
                        if not footage_allowed(credit["source"],era,credit.get("metadata_text","")):
                            raise ValueError("historical_era_mismatch")
                        download_photo(url,path,size=size)
                        if require_verified:
                            credit.update(verify_photo(path,subject,query,matcher))
                    except Exception:
                        path.unlink(missing_ok=True)
                        continue
                    seen.add(key)
                    credit.update(chapter=index,subject=subject)
                    selected.append((path,credit))
            except Exception as exc:
                print("[STILL SOURCE UNAVAILABLE]",provider.__name__,type(exc).__name__,flush=True)
    if selected: return selected
    if require_verified:
        raise RuntimeError("No licensed subject-verified photo; refuse unrelated or generated filler")
    return list(illustrations(chapter,index,directory))

def render_recovery(index,audio,duration,chapter,work,seen,run):
    photos=stills(chapter,index,work,seen)
    directory=work/f"recovery-{index:02d}"
    directory.mkdir(parents=True,exist_ok=True)
    files=[]
    # Cover every audio frame using real photos with subtle motion, or marked cards.
    total=round(duration*30)
    for i,(path,credit) in enumerate(photos):
        n=round((i+1)*total/len(photos))-round(i*total/len(photos))
        dest=directory/f"shot-{i:02d}.mp4"
        vf=("scale=2400:1350,zoompan=z='min(1.10,1+on*0.10/"+str(max(n,1))+")':"
            "x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d="+str(n)+
            ":s=1920x1080:fps=30,setsar=1,format=yuv420p")
        run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
             "-i",str(path),"-vf",vf,"-frames:v",str(n),"-an","-threads","2",
             "-c:v","libx264","-preset","veryfast","-crf","25",str(dest)],600)
        credit["chapter"]=index
        files.append(dest)
    manifest=directory/"concat.txt"
    manifest.write_text("".join("file '"+str(p.resolve())+"'\n" for p in files))
    output=work/f"chapter-{index:02d}.mp4"
    run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
         "-f","concat","-safe","0","-i",str(manifest),"-i",str(audio),
         "-map","0:v:0","-map","1:a:0","-t",f"{duration:.3f}","-c:v","copy",
         "-c:a","aac","-b:a","160k",str(output)],900)
    return output,[credit for _,credit in photos]
