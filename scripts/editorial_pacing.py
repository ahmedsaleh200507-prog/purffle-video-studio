"""Bounded editorial preferences, never replacements for validation."""
import math
import os

def enabled():
    return os.getenv("PURFFLE_EDITORIAL_PACING")=="1"

def better_opening(candidate,incumbent,*,minimum_gain=4.):
    """Prefer a clearly improved, independently verified opening only."""
    a,b=float(candidate),float(incumbent)
    return math.isfinite(a) and math.isfinite(b) and 0<=a<=150 and 0<=b<=150 and a>=b+minimum_gain

def pacing_report(durations):
    values=[float(v) for v in durations]
    if not values or any(not math.isfinite(v) or v<=0 for v in values):
        raise ValueError("Invalid measured scene durations")
    return {"state":"measured","scene_count":len(values),
            "mean_scene_seconds":round(sum(values)/len(values),2),
            "longest_scene_seconds":round(max(values),2),
            "scenes_over_six_seconds":[i+1 for i,v in enumerate(values) if v>6],
            "scope":"Narrated scene timing, not actual camera cuts or retention prediction",
            "recommendation":"Prefer verified new footage when the story advances; do not insert meaningless cuts."}
