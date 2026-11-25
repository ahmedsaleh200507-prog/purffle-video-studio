"""Independent bounded event and theme observations, not semantic ground truth."""
import math
import os
import threading

_LOCK=threading.Lock()
_COUNTS={"event":0,"theme":0}
_LIMITS={"event":4,"theme":6}

def compare(rows, expected):
    if not rows or len(rows)!=expected or any(len(r)!=2 for r in rows):
        raise ValueError("Invalid contrast matrix")
    margins=[float(r[0])-float(r[1]) for r in rows]
    if not all(math.isfinite(float(v)) for r in rows for v in r):
        raise ValueError("Non-finite contrast")
    wins=sum(m>0 for m in margins)
    return {"matching_frames":wins,"sampled_frames":len(rows),
            "margins":[round(m,4) for m in margins],
            "agrees":wins>len(rows)/2}

def motion_pair(before,after):
    """Exposure-resistant image change; may include camera motion."""
    from PIL import Image,ImageChops,ImageFilter,ImageStat
    a,b=[f.convert("L").resize((96,96)).filter(ImageFilter.GaussianBlur(.8))
         for f in (before,after)]
    signed=ImageChops.subtract(b,a,scale=2,offset=128)
    midpoint=int(ImageStat.Stat(signed).median[0])
    residual=ImageChops.difference(signed,Image.new("L",signed.size,midpoint))
    hist=residual.histogram()
    fraction=sum(hist[4:])/9216
    return {"changed_fraction":round(fraction,4),
            "mean_residual":round(ImageStat.Stat(residual).mean[0],4),
            "localized_change_observed":fraction>=.01,
            "scope":"image change only; camera motion or cuts may cause change"}

def observe(kind,frames,prompts,scorer=None):
    if os.environ.get("PURFFLE_EVENT_THEME_REVIEW")!="1":
        return {"state":"disabled"}
    if not frames or len(prompts)!=2 or kind not in _LIMITS:
        return {"state":"invalid_input"}
    with _LOCK:
        if _COUNTS[kind]>=_LIMITS[kind]:
            return {"state":"budget_exhausted"}
        _COUNTS[kind]+=1
    try:
        if scorer is None:
            from siglip_review import score
            scorer=score
        return {"state":"observed",**compare(scorer(frames,prompts),len(frames)),
                "scope":"relative SigLIP scores, not calibrated accuracy or an event verdict"}
    except Exception as exc:
        return {"state":"unavailable","error_type":type(exc).__name__}

def observe_theme(frames,topic,subject,specification=None):
    if specification:
        positive=specification["positive"]
        negative=" ".join(specification["negatives"])
    else:
        positive=f"Real documentary imagery of {subject}, illustrating {topic}."
        negative=f"Unrelated scenery or an empty background without {subject}."
    return observe("theme",frames,[positive[:400],negative[:400]])
