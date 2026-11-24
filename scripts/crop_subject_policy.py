"""Independent subject screening on the actual exported crop, not full frame."""
def verify_crop_subject(frames,spec,matcher):
    from media_validation import scene_specific_hard_negatives
    if len(frames)<3:
        raise ValueError("Crop subject screening requires three decoded frames")
    subject=" ".join(x for x in (spec.main_character,spec.object) if x).strip()
    if not subject:
        raise ValueError("Missing subject for crop")
    captions=[f"A real documentary video frame showing {subject}.",
        f"A real video frame of {spec.visual_search_query}.",
        "An unrelated empty background without the requested subject.",
        "A drawing, cartoon or computer generated illustration.",
        *scene_specific_hard_negatives(spec)]
    rows=matcher._similarities(frames,captions)
    if len(rows)!=len(frames) or any(len(r)!=len(captions) for r in rows):
        raise ValueError("Crop subject score shape invalid")
    # Subject must survive the crop; event verification remains separate.
    threshold=max(.19,float(getattr(matcher,"threshold",.23))-.04)
    good=[r[0]>=threshold and r[1]>=threshold-.015 and r[0]-max(r[2:])>=.004 for r in rows]
    if sum(good)<2:
        raise ValueError("Actual output crop lacks the requested subject in two of three frames")
    return {"verified":True,"method":"clip_actual_crop_subject","matching_frames":sum(good),
            "sample_count":len(rows),"subject_scores":[round(r[0],4) for r in rows],
            "threshold":threshold,"limitations":"Sampled visual similarity, not identity or geolocation proof"}
