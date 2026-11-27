"""Explain independent evidence without converting scores or captions to truth."""
def summarize(match):
    crop=match.get("crop_subject_proof") or {}
    second=crop.get("siglip_shadow_review") or {}
    vlm=crop.get("visual_language_review") or match.get("visual_language_review") or {}
    framing=match.get("object_framing") or {}
    event=match.get("director_check") or {}
    evidence={
        "clip":"passed" if crop.get("verified") else "not_observed",
        "siglip":("agrees" if second.get("agrees") is True else "disagrees"
                  if second.get("agrees") is False else "not_observed"),
        "dino":framing.get("state","not_observed"),
        "bytetrack":(framing.get("tracking_agreement") or {}).get("state","not_observed"),
        "florence":(vlm.get("models",{}).get("florence") or {}).get("state","not_observed"),
        "qwen":(vlm.get("models",{}).get("qwen") or {}).get("state","not_observed"),
        "event":event.get("verified") if event.get("event_required") else None,
        "motion":(event.get("event_nearby_motion") or {}).get("localized_change_observed"),
        "scene_boundaries":((match.get("action_window") or {}).get("scene_boundaries") or {}).get("state","not_observed"),
    }
    state="secondary_disagreement" if evidence["siglip"]=="disagrees" else (
        "sampled_subject_corroborated" if evidence["clip"]=="passed" and evidence["siglip"]=="agrees" else "partial_evidence")
    return {"state":state,"evidence":evidence,
            "scope":"independent observations; captions and motion do not establish semantic action or identity"}
