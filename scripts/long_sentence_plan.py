"""Actual aligned sentence timing and immutable per-shot visual plans."""
import json
import re

def tokens(text):
    return re.findall(r"\w+",str(text).casefold())

def timed_groups(text,words,duration,max_groups=6):
    chunks=[x.strip() for x in re.split(r"(?<=[.!?])\s+",text.strip()) if x.strip()]
    if not chunks or not words or duration<=0:
        raise ValueError("Missing narration alignment")
    while len(chunks)>max_groups:
        k=min(range(len(chunks)-1),key=lambda i:len(chunks[i])+len(chunks[i+1]))
        chunks[k:k+2]=[chunks[k]+" "+chunks[k+1]]
    if tokens(" ".join(w.text for w in words))!=tokens(text):
        raise ValueError("Alignment differs from approved narration")
    def bounds_for(parts):
        total=cursor=consumed=0
        bounds=[0]
        for part in parts[:-1]:
            total+=len(tokens(part))
            while cursor<len(words) and consumed<total:
                consumed+=len(tokens(words[cursor].text))
                cursor+=1
            if consumed!=total or cursor>=len(words):
                raise ValueError("Cannot align sentence boundary")
            bounds.append(round(float(words[cursor].start)*30))
        bounds.append(round(float(duration)*30))
        if any(b<=a for a,b in zip(bounds,bounds[1:])):
            raise ValueError("Nonmonotonic sentence boundaries")
        return bounds
    while True:
        bounds=bounds_for(chunks)
        lengths=[b-a for a,b in zip(bounds,bounds[1:])]
        if min(lengths)>=60 or len(chunks)==1:
            break
        k=min(lengths.index(min(lengths)),len(chunks)-2)
        chunks[k:k+2]=[chunks[k]+" "+chunks[k+1]]
    return [{"index":i+1,"narration":part,"start_frame":bounds[i],
        "end_frame":bounds[i+1],"seconds":(bounds[i+1]-bounds[i])/30}
        for i,part in enumerate(chunks)]

SCHEMA={"type":"object","properties":{"shots":{"type":"array","items":{
    "type":"object","properties":{"index":{"type":"integer"},"visual_subject":{"type":"string"},
    "visual_search_query":{"type":"string"},"location":{"type":"string"}},
    "required":["index","visual_subject","visual_search_query","location"],"additionalProperties":False}}},
    "required":["shots"],"additionalProperties":False}

def validate_plan(raw,groups,chapter,topic):
    from geography_policy import named_regions,specific
    rows=raw.get("shots") if isinstance(raw,dict) else None
    if not isinstance(rows,list) or len(rows)!=len(groups):
        raise ValueError("Every timed group requires a plan")
    result=[]
    for group,row in zip(groups,rows):
        if not isinstance(row,dict) or set(row)!={"index","visual_subject","visual_search_query","location"} or row["index"]!=group["index"]:
            raise ValueError("Visual plan sequence changed")
        if any(not isinstance(row[k],str) for k in ("visual_subject","visual_search_query","location")):
            raise ValueError("Invalid visual fields")
        subject=" ".join(row["visual_subject"].split())
        query=" ".join(row["visual_search_query"].split())
        location=" ".join(row["location"].split())
        if not (3<=len(subject)<=50 and 4<=len(query)<=110 and len(location)<=70 and len(query.split())<=12):
            raise ValueError("Invalid search terms")
        if not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 '\-]*",x) for x in (subject,query)):
            raise ValueError("Search terms must be simple English")
        spoken=named_regions(group["narration"])
        context=named_regions(topic+" "+str(chapter.get("title",""))+" "+str(chapter.get("visual_search_query","")))
        planned=named_regions(" ".join((subject,query,location)))
        if planned-(spoken|context):
            raise ValueError("Invented named location")
        result.append({**group,"visual_subject":subject,"visual_search_query":query,
            "location":location,"required_regions":specific(spoken or context)})
    return result

def plan_chapter(client,groups,chapter,topic):
    from long_generic import _completion
    prompt=("Return one real documentary stock-video search plan for each immutable narration group. "
        "Use simple English visible subject and query. Location must be empty unless explicitly mentioned. "
        "For invisible mechanisms select an appropriate visible subject, never invent an event. "
        "Do not change narration or introduce facts. Topic: "+topic+"\nChapter: "+str(chapter.get("title",""))+"\n"+
        json.dumps([{"index":x["index"],"narration":x["narration"]} for x in groups],ensure_ascii=False))
    for attempt in range(2):
        try:
            return validate_plan(_completion(client,prompt,SCHEMA,"timed_visual_plan",max_tokens=1400,fallback=bool(attempt)),groups,chapter,topic)
        except (ValueError,TypeError,KeyError,RuntimeError):
            pass
    raise RuntimeError("No validated timed visual plan")

def crop_proof(path,seconds,subject,query,matcher):
    from PIL import ImageOps
    from media_validation import _frame,SceneSpec,scene_specific_hard_negatives,ValidationError
    spec=SceneSpec(main_character="",object=subject,action="ambient",visual_search_query=query)
    frames=[ImageOps.fit(_frame(path,max(0,min(seconds-.15,t)),448,preserve_aspect=True),(448,252))
        for t in (.2,seconds*.45,seconds*.8)]
    captions=[f"A real documentary video of {query}.",f"A real video showing {subject}.",
        "An unrelated landscape or empty background.","A drawing or computer animation.",
        *scene_specific_hard_negatives(spec)]
    scores=matcher._similarities(frames,captions)
    matching=sum(row[0]>=.22 and row[1]>=.18 and row[0]-max(row[2:])>=.008 for row in scores)
    if matching<2:
        raise ValidationError("Centered 16:9 crop lacks planned subject")
    from siglip_review import observe
    return {"method":"centered_16_9_clip","matching_moments":matching,"verified":True,
            "siglip_shadow_review":observe(frames,subject,query)}
