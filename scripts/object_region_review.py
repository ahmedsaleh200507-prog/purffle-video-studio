"""Independent region screening for open-vocabulary box proposals.

CLIP is a second imperfect model, not ground truth. No verified boxes means
retain the existing framing; never reject the entire footage on this basis.
"""
import math

def corroborate(frame, subject, detections, scorer=None):
    if not detections:
        return {"accepted": [], "checks": []}
    subject = " ".join(str(subject).split())[:120]
    if not subject:
        return {"accepted": [], "checks": []}
    if scorer is None:
        from media_validation import SceneMatcher
        scorer = SceneMatcher()._similarities
    from video_first_policy import contrast_prompts
    prompts = [f"A real photograph showing {subject}.",
               "An empty patch of background or scenery.",
               "A close-up of a surface texture or a pattern.",
               "An unrecognizable object or an unrelated fragment.",
               *contrast_prompts(subject,subject)]
    crops, candidates = [], []
    w,h=frame.size
    for d in detections[:6]:
        b=d.get("box",[])
        if len(b)!=4 or not all(math.isfinite(v) and 0<=v<=1 for v in b):
            continue
        x0,y0,x1,y1=b
        if x1<=x0 or y1<=y0:
            continue
        px=(x1-x0)*.2
        py=(y1-y0)*.2
        rect=(max(0,math.floor((x0-px)*w)),max(0,math.floor((y0-py)*h)),
              min(w,math.ceil((x1+px)*w)),min(h,math.ceil((y1+py)*h)))
        if rect[2]-rect[0]<12 or rect[3]-rect[1]<12:
            continue
        crops.append(frame.crop(rect))
        candidates.append(d)
    if not crops:
        return {"accepted":[],"checks":[]}
    rows=scorer(crops,prompts)
    if len(rows)!=len(crops) or any(len(r)!=len(prompts) for r in rows):
        raise ValueError("Region verifier score shape invalid")
    checks, accepted=[],[]
    for d,row in zip(candidates,rows):
        if not all(math.isfinite(v) for v in row):
            raise ValueError("Region verifier score not finite")
        margin=row[0]-max(row[1:])
        ok=row[0]>=.19 and margin>=.01
        checks.append({"box":d["box"],"detector_score":d["score"],
                       "clip_subject":round(row[0],4),"clip_margin":round(margin,4),
                       "accepted":ok})
        if ok:
            accepted.append(d)
    return {"accepted":accepted,"checks":checks}
