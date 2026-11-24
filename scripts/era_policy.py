"""Keep archival footage out of modern scenes, including recovery paths."""
import re

ARCHIVAL_SOURCE="loc-video"
HISTORY=re.compile(r"\b(?:archival|archive footage|historical footage|historic film|historical film|vintage|silent film|early cinema|old[- ]fashioned|historic(?:al)? (?:factory|city|street|train|cars?|machinery|footage)|historische[nrsm]? (?:aufnahmen|filme?|fabrik|züge|straßen)|archivaufnahmen|stummfilm|frühere[nrsm]? (?:fabrik|industrie))\b",re.I)
MODERN=re.compile(r"\b(?:modern|modern[- ]day|today|present[- ]day|contemporary|current|nowadays|today's|heute|heutig\w*|gegenwärtig\w*|moderne\w*|aktuell\w*|21st century|21\. jahrhundert)\b",re.I)
YEAR=re.compile(r"(?<!\d)((?:18|19|20)\d{2})(s|er(?:-jahre)?)?(?!\d)",re.I)
def intervals(text):
    values=[]
    for m in YEAR.finditer(text):
        year=int(m.group(1))
        if m.group(2):
            values.append((year//10*10,year//10*10+9))
        else:
            values.append((year,year))
    return values

def scene_era(plan):
    plan=plan or {}
    # Deliberately omit the overall topic: a history-of-technology film can
    # contain both a 1900 factory scene and a modern robotics scene.
    text=" ".join(str(plan.get(k) or "") for k in
                  ("visual_search_query","visual_subject","object","time","title","action"))
    years=intervals(text)
    historical=[x for x in years if x[1]<2000]
    current=bool(MODERN.search(text) or any(x[0]>=2000 for x in years))
    if current:
        return {"mode":"modern_or_mixed","years":[]}
    if historical or HISTORY.search(text):
        return {"mode":"historical","years":historical}
    return {"mode":"unspecified","years":[]}

def source_allowed(source,era):
    return source!=ARCHIVAL_SOURCE or era["mode"]=="historical"

def footage_allowed(source,era,metadata="",recorded_date=""):
    if not source_allowed(source,era):
        return False
    # Archive markers are explicit evidence, not a guess from black-and-white
    # aesthetics, a publisher name or an item's numerical identifier.
    archival=source==ARCHIVAL_SOURCE or bool(HISTORY.search(str(metadata)))
    dates=intervals(str(recorded_date))
    if not dates and archival:
        dates=intervals(str(metadata))
    old=bool(dates and all(end<2000 for _,end in dates))
    if era["mode"]!="historical":
        return not (archival or old)
    if era["years"]:
        # Fail closed for LOC and explicitly archival material when the
        # requested date cannot be established. Other stock can illustrate
        # a scene only if there is no contradictory explicit date.
        if not dates:
            return not archival
        return any(a<=d and c<=b for a,b in era["years"] for c,d in dates)
    if source==ARCHIVAL_SOURCE and dates and not old:
        return False
    return True
