"""Shared visual relevance and footage-duration audit."""
import re
import math
def contrast_prompts(subject,query):
    text=(str(subject)+" "+str(query)).casefold()
    negatives=[]
    if re.search(r"\b(whales?|humpbacks?|dolphins?|sharks?|seals?)\b",text):
        negatives+=["Open ocean and ordinary waves with no marine animal visible.",
                    "A distant splash or foam on empty water without a visible marine animal."]
    if re.search(r"bioluminescen|glowing (ocean|sea|plankton|wave)|glowing marine|leuchtend",text):
        negatives+=["Ordinary blue ocean water and white sea foam in daylight.",
                    "Blue colored water without visibly luminous organisms.",
                    "A sunset or moonlight reflection on ordinary water."]
    if re.search(r"\b(owls?|eagles?|birds?)\b",text):
        negatives+=["Empty trees, branches and sky without a visible bird."]
    return negatives

def check_topic_metadata(topic,metadata):
    from media_validation import reject_offtopic_science_source
    from topic_footage import (contradicts_floating_ship,is_lava_ocean_topic,
        lava_subject_in_metadata,is_glowing_ocean_topic,bioluminescence_visible_in_metadata)
    reject_offtopic_science_source(topic,metadata)
    if contradicts_floating_ship(topic,metadata):
        raise ValueError("Unrelated wreck instead of floating ship")
    if is_lava_ocean_topic(topic) and not lava_subject_in_metadata(metadata):
        raise ValueError("No volcanic subject in source metadata")
    if is_glowing_ocean_topic(topic) and not bioluminescence_visible_in_metadata(metadata):
        raise ValueError("Ordinary ocean is not bioluminescence")

def media_mix(credits):
    totals={"video":0.,"photo":0.,"other":0.}
    for c in credits:
        n=float(c.get("screen_seconds",c.get("shot_seconds",0)))
        if not math.isfinite(n) or n<0: raise ValueError("Invalid screen duration")
        kind=c.get("media_type")
        totals[kind if kind in ("video","photo") else "other"]+=n
    total=sum(totals.values())
    ratio=totals["video"]/total if total else 0.
    return {"video_seconds":round(totals["video"],3),"photo_seconds":round(totals["photo"],3),
            "other_seconds":round(totals["other"],3),"video_share":round(ratio,4),
            "target_video_share":.8,"video_majority":ratio>.5,
            "target_met":ratio>=.8,"measured_screen_time":bool(total)}
