"""Topic-focused reference retrieval for the single-pass narration path.

Search hints are not evidence. Only fetched Wikipedia passages enter the
writer/reviewer. All requests use a fixed public endpoint and bounded payloads.
"""
import json
import re
from urllib.parse import quote
from story_room import StoryRoom
from science_sources import Evidence, _search_text, _STOP, _WEAK_TITLE_TERMS
from topic_footage import words

PREFERRED=("gemini-3.1-flash-lite","openai/gpt-oss-20b","openai/gpt-oss-120b","qwen/qwen3.8-27b")
SCHEMA={"type":"object","properties":{"english":{"type":"string"},"native":{"type":"string"},"focus":{"type":"string"}},
        "required":["english","native","focus"],"additionalProperties":False}

def search_plan(topic,language,room=None):
    room=room or StoryRoom()
    fallback=_search_text(topic)
    try:
        result,_=room.ask("research","Find the exact encyclopedia article topic that answers this question, not its broad subject. "
            "Return a short English Wikipedia article/search phrase, a short article/search phrase in the requested language, "
            "and a short English phrase identifying the direct mechanism or practical purpose, not a disputed theory or peripheral detail. "
            "These are search hints only, not factual claims. No URLs. "
            f"Language: {language}. Question: {topic}",SCHEMA,PREFERRED,temperature=.1)
        en,native,focus=(str(result[k]).strip()[:100] for k in ("english","native","focus"))
    except RuntimeError:
        en,native,focus="","",fallback
    queries=[("en",en),("de" if language=="de" else "en",native),
             ("de" if language=="de" else "en",topic),("en",focus)]
    return list(dict.fromkeys((lang,q) for lang,q in queries if q))[:4],focus or fallback

def _get(client,lang,params):
    with client.get(f"https://{lang}.wikipedia.org/w/api.php",
        params={**params,"format":"json","formatversion":2},
        headers={"User-Agent":"PurffleVideoStudio/4.0 (+https://github.com/ahmedsaleh200507-prog/purffle-video-studio)","Accept":"application/json"},
        timeout=(6,15),allow_redirects=False,stream=True) as response:
        if response.status_code!=200:
            raise RuntimeError("reference_http_"+str(response.status_code))
        data=bytearray()
        for chunk in response.iter_content(16384):
            data.extend(chunk)
            if len(data)>500000: raise RuntimeError("reference_payload_limit")
        return json.loads(data)

def _terms(text):
    return {t for t in words(text) if len(t)>2 and t not in _STOP and t not in _WEAK_TITLE_TERMS}

def _match(left,right):
    return sum(any(t==u or (min(len(t),len(u))>=5 and (t.startswith(u) or u.startswith(t))
                       and abs(len(t)-len(u))<=3) for u in right) for t in left)

def passages(extract,query,focus,topic):
    """Choose real contiguous paragraphs, including relevant article sections."""
    query_terms,focus_terms,topic_terms=map(_terms,(query,focus,topic))
    ranked=[]
    extract=re.sub(r"(?m)^=+[^\n]*=+[ \t]*$", "\n\n", extract)
    for i,raw in enumerate(re.split(r"\n\s*\n",extract)):
        paragraph=re.sub(r"\s+"," ",raw).strip()
        if len(paragraph)<80 or paragraph.startswith("==") or "may refer to:" in paragraph[:150].casefold():
            continue
        # Bound paragraphs without fabricating joins or claims.
        if len(paragraph)>2200:
            paragraph=paragraph[:2200].rsplit(" ",1)[0]
        terms=_terms(paragraph)
        rank=5*_match(focus_terms,terms)+3*_match(query_terms,terms)+_match(topic_terms,terms)
        if rank: ranked.append((rank,i,paragraph))
    ranked.sort(key=lambda x:(-x[0],x[1]))
    return ranked[:3]

def discover(topic,language,*,session=None,room=None):
    import requests
    client=session or requests.Session()
    queries,focus=search_plan(topic,language,room)
    visited=set()
    candidates=[]
    for query_index,(lang,query) in enumerate(queries):
        try:
            result=_get(client,lang,{"action":"query","list":"search","srsearch":query,"srnamespace":0,"srlimit":3})
        except (requests.RequestException,RuntimeError,ValueError,OSError):
            continue
        for hit_index,hit in enumerate(result.get("query",{}).get("search",[])[:2]):
            pageid=hit.get("pageid")
            if not pageid or (lang,pageid) in visited: continue
            visited.add((lang,pageid))
            try:
                result=_get(client,lang,{"action":"query","pageids":pageid,"prop":"extracts","explaintext":1,"exsectionformat":"wiki"})
            except (requests.RequestException,RuntimeError,ValueError,OSError):
                continue
            for page in result.get("query",{}).get("pages",[]):
                title=str(page.get("title","")).strip()
                extract=str(page.get("extract",""))
                if not title or page.get("missing") or len(extract)<100: continue
                title_score=_match(_terms(query),_terms(title))
                if not title_score: continue
                ranked=passages(extract,query,focus,topic)
                # Reserve the exact search hit introduction as well as focused body sections.
                lead=re.sub(r"\s+"," ",extract.split("\n\n",1)[0]).strip()
                if query_index<=1 and hit_index==0 and len(lead)>=100:
                    if len(lead)>2200: lead=lead[:2200].rsplit(" ",1)[0]
                    candidates.append((10000-query_index,lang,title,0,lead))
                for score,order,p in ranked:
                    candidates.append((score+3*title_score-8*query_index-hit_index,lang,title,order,p))
    candidates.sort(key=lambda x:-x[0])
    chosen=[]
    seen=set()
    per_article={}
    for score,lang,title,order,p in candidates:
        key=(lang,title)
        if p in seen or per_article.get(key,0)>=3: continue
        seen.add(p)
        per_article[key]=per_article.get(key,0)+1
        chosen.append({"id":f"ref-{len(chosen)+1}","title":title,
            "url":f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ','_'),safe='()')}",
            "tier":"community_edited_reference","license":"CC BY-SA (see linked article and history)",
            "excerpt":p})
        if len(chosen)>=6: break
    if not chosen:
        raise RuntimeError("science_sources_unavailable: no focused reference passages")
    print("[REFERENCE PLAN]",json.dumps({"topic":topic,"queries":queries,"focus":focus,
        "sources":[s["title"] for s in chosen]},ensure_ascii=False),flush=True)
    return Evidence(str(topic),tuple(chosen),"model_screened_reference")
