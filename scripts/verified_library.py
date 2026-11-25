"""Small reusable public-domain source index, never a footage approval cache.

No video bytes or signed URLs are persisted across jobs. Every hit must pass
normal download, current scene, license, resolution, motion and crop checks.
"""
import json
import math
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

SOURCES={"usgs-video","nps-video","wikimedia-video","archive-video","nasa-video"}
MAX_ROWS=120
MAX_AGE=30*86400

def enabled():
    return os.environ.get("PURFFLE_VERIFIED_LIBRARY")=="1"

def public_url(value):
    try:
        u=urlsplit(str(value))
        return (u.scheme=="https" and bool(u.hostname) and not u.username
                and not u.password and u.port in (None,443)
                and not u.query and not u.fragment)
    except ValueError:
        return False

def safe_text(value,limit=600):
    text=str(value or "")
    if re.search(r"https?://|bearer\s|api[_-]?key|token=|secret=",text,re.I):
        return ""
    return text[:limit]

def eligible(row):
    from video_sources import LicenseValidator
    lic=row.get("license",{})
    return (row.get("source") in SOURCES and isinstance(lic,dict)
            and lic.get("id") in {"CC0-1.0","PDM-1.0"}
            and not lic.get("attribution_required")
            and LicenseValidator.validate(lic)
            and all(public_url(row.get(k)) for k in ("url",))
            and public_url(lic.get("source_page")) and public_url(lic.get("url"))
            and bool(row.get("id")) and bool(row.get("text"))
            and bool(row.get("subject")))

def read_rows(path):
    try:
        path=Path(path)
        if not path.is_file() or path.stat().st_size>512*1024:
            return []
        rows=json.loads(path.read_text(encoding="utf8"))
        if not isinstance(rows,list):
            return []
        result=[]
        for row in rows[:MAX_ROWS]:
            if not isinstance(row,dict):
                continue
            try:
                age=time.time()-float(row["saved_at"])
                if 0<=age<=MAX_AGE and eligible(row):
                    result.append(row)
            except (TypeError,ValueError,KeyError,AttributeError):
                continue
        return result
    except (OSError,ValueError,TypeError):
        return []

def remember(path,item,spec,source_quality):
    if not enabled():
        return False
    raw=item.extra.get("license",{})
    if not isinstance(raw,dict):
        return False
    lic={k:raw.get(k) for k in ("id","url","source_page","creator","attribution_required")}
    lic["creator"]=safe_text(lic.get("creator"),150)
    lic["attribution"]=" | ".join(str(lic.get(k) or "") for k in ("creator","id","url","source_page"))
    row={"source":item.source,"id":safe_text(item.id,200),"url":str(item.url),
         "text":safe_text(item.text,1000),"subject":safe_text(spec.object,150),
         "query":safe_text(spec.visual_search_query,200),"license":lic,
         "recorded_date":safe_text(item.extra.get("recorded_date"),80),
         "width":int(source_quality["width"]),"height":int(source_quality["height"]),
         "duration":float(source_quality["duration"]),"saved_at":time.time()}
    # Partial downloads describe a selected interval, not the complete URL.
    if item.extra.get("download_evidence",{}).get("mode")!="full_download":
        return False
    if not eligible(row) or not math.isfinite(row["duration"]) or row["duration"]<=0:
        return False
    path=Path(path)
    rows=[x for x in read_rows(path) if (x["source"],x["id"])!=(row["source"],row["id"])]
    rows=[row]+rows[:MAX_ROWS-1]
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(rows,ensure_ascii=False),encoding="utf8")
    temp.replace(path)
    return True

def candidates(path,registry,spec,queries,need,allowed_sources):
    if not enabled():
        return []
    from topic_footage import words
    subject=words(spec.object)
    if not subject:
        return []
    terms=set().union(*(words(q) for q in queries))
    rows=[]
    for r in read_rows(path):
        try:
            if r["source"] not in allowed_sources or r["source"] not in registry.enabled:
                continue
            if float(r["duration"])<float(need) or min(int(r["width"]),int(r["height"]))<720:
                continue
            if not subject.issubset(words(r["subject"])|words(r["text"])):
                continue
            overlap=len(terms & (words(r["query"])|words(r["text"])))
            if overlap<1:
                continue
            rows.append((overlap,r))
        except (ValueError,TypeError,KeyError):
            continue
    output=[]
    for _,r in sorted(rows,key=lambda v:(-v[0],-v[1]["saved_at"]))[:3]:
        item=registry._item(r["source"],r["id"],r["url"],spec.visual_search_query,0,
                            r["text"],r["license"],r["width"],r["height"],r["duration"])
        if item is not None:
            item.extra["recorded_date"]=r.get("recorded_date","")
            item.extra["verified_library_candidate"]=True
            output.append(item)
    return output
