"""Opt-in bridge from StrictVisuals to the proven exact-frame assembler.

Every short shot must pass the original spoken-scene contract. This does not
relax source, action, license, geography, motion or resolution gates.
"""
import copy
import json
import math
import os
import tempfile
import time
from pathlib import Path
from multi_shot import assemble,frame_plan,validate_plan,digest

def enabled():
    return os.getenv("PURFFLE_MULTI_SHOT")=="1"

def review_rendered(path,length,row,matcher):
    from media_validation import SceneSpec,_frame
    from visual_director import verify_visible_event_or_illustrative_subject
    from siglip_review import check
    from source_overlay import check_source
    from crop_subject_policy import verify_crop_subject
    spec=SceneSpec.from_dict(row["plan"])
    match=matcher.match(path,spec,metadata=row["metadata_text"],duration=length,
        allow_sparse_metadata=row["pixel_review_required"])
    frames=[_frame(path,length*f,448,preserve_aspect=True) for f in (.15,.5,.85)]
    crop=verify_crop_subject(frames,spec,matcher)
    independent=check(frames,spec.object,spec.visual_search_query)
    event=verify_visible_event_or_illustrative_subject(path,length,.5,row["director_contract"],
        match,scorer=matcher._similarities,opening=row["opening"])
    text=check_source(path,length,.5)
    return {"verified":crop["verified"] is True and independent["agrees"] is True and event["verified"] is True,
            "crop":crop,"siglip":independent,"event":event,"overlay":text}

def collect(visuals,idx,query,payload,topic,need,dest,settings,deadline,*,assembler=assemble,reviewer=review_rendered):
    from studio_runtime import _atomic_json
    fps=int(settings.fps)
    # Reserve the same extra 0.05s required by strict_prepare_segment.
    counts=frame_plan(float(need)+.10,fps)
    before=len(visuals.report["scenes"])
    snapshot=tuple(x.copy() for x in (visuals.used,visuals.used_urls,visuals.used_hashes,visuals.credits))
    state=visuals.state_path
    original_state=state.read_bytes() if state.exists() else None
    # Long-shot rejections are not transferable to shorter intervals.
    # Keep shared permanent technical rejections and all duplicate ledgers.
    old_rejections=visuals._rejected_candidates
    visuals._rejected_candidates=set()
    target=None
    items,shots,records=[],[],[]
    try:
        for n in counts:
            if time.monotonic()>=deadline:
                raise RuntimeError("multi-shot search budget exhausted")
            visuals._shot_deadline=deadline
            start=len(visuals.report["scenes"])
            length=n/fps
            item=visuals.for_scene(idx,query,json.dumps(payload),topic,length,dest)
            rows=[r for r in visuals.report["scenes"][start:] if r.get("status")=="selected"]
            if len(rows)!=1:
                raise RuntimeError("missing independent short-shot selection")
            row=rows[0]
            match=row["match"]
            if (item.extra.get("strict_validated") is not True
                    or match.get("director_check",{}).get("verified") is not True
                    or row["director_contract"]!=payload["_visual_contract"]
                    or float(row["required_seconds"])+1e-6<length):
                raise ValueError("short shot not approved for spoken scene")
            sparse=bool(item.extra.get("relevance_evidence",{}).get("pixel_review_required"))
            if sparse and match.get("pixel_first_proof",{}).get("verified") is not True:
                raise ValueError("missing required pixel-first evidence")
            shots.append({"path":str(item.path),"id":row["id"],"source":row["source"],
                "sha256":row["sha256"],"original_sha256":row["original_sha256"],
                "license":row["license"],"start":0.,"focus":float(match.get("crop_focus_x",.5)),
                "plan":row["plan"],"metadata_text":row.get("metadata_text",""),
                "director_contract":row["director_contract"],"opening":idx==0,
                "pixel_review_required":sparse,"source_match":match,
                "source_quality":row["quality"],
                "approval":{"verified":True,"sha256":row["sha256"],"start":0.,"seconds":length}})
            items.append(item)
            records.append(row)
        verify_distinct(shots)
        with tempfile.TemporaryDirectory(dir=dest) as tmp:
            # The assembler refuses existing files; use a unique reserved directory.
            temp=Path(tmp)/"bundle.mp4"
            result=assembler(shots,counts,temp,width=settings.width,height=settings.height,fps=fps,
                review=lambda p,d,r:reviewer(p,d,r,visuals.matcher))
            validate_bundle(result,payload["_visual_contract"])
            if digest(temp)!=result["sha256"]:
                raise ValueError("assembled source digest mismatch")
            fd,name=tempfile.mkstemp(prefix="verified-multishot-",suffix=".mp4",dir=dest)
            os.close(fd)
            target=Path(name)
            temp.replace(target)
        item=copy.copy(items[0])
        item.extra=copy.deepcopy(items[0].extra)
        item.path=target
        item.width,item.height=settings.width,settings.height
        item.duration=float(result["duration"])
        quality=visuals.quality.validate(target,need=need)
        match=copy.deepcopy(records[0]["match"])
        match["crop_focus_x"]=.5
        match["director_check"]={"verified":True,"method":"individually_verified_multishot_contract",
            "shot_count":len(shots),"event_required":payload["_visual_contract"]["event_required"]}
        match["multi_shot"]={"state":"verified_bundle","shot_count":len(shots)}
        layout={"mode":"verified_multishot","foreground_scale":1.0}
        item.extra.update(match=match,quality=quality,portrait_layout=layout,
            sha256=result["sha256"],multi_shot=result,strict_validated=True)
        final=copy.deepcopy(records[0])
        final.update(downloaded_file=str(target),sha256=result["sha256"],quality=quality,
            match=match,multi_shot=result,required_seconds=need,portrait_layout=layout,
            crop={"focus_x":.5,"crop_scale":1.0})
        # The first source fields remain for compatibility. Complete individual
        # licenses, source hashes and review evidence live in multi_shot.shots.
        visuals.used_hashes.add(result["sha256"])
        _atomic_json(state,{"keys":sorted(visuals.used),"urls":sorted(visuals.used_urls),"hashes":sorted(visuals.used_hashes)})
        visuals.report["scenes"][before:]=[final]
        visuals._save()
        print("[MULTI SHOT SELECTED]",idx+1,len(shots),result["duration"],flush=True)
        return item,final
    except BaseException:
        visuals.used,visuals.used_urls,visuals.used_hashes,visuals.credits=snapshot
        if original_state is None:
            state.unlink(missing_ok=True)
        else:
            state.write_bytes(original_state)
        if target is not None:
            target.unlink(missing_ok=True)
        for row in visuals.report["scenes"][before:]:
            if row.get("status")=="selected":
                row["status"]="discarded_partial_multishot"
        visuals._save()
        raise
    finally:
        visuals._rejected_candidates=old_rejections

def verify_distinct(shots):
    seen=set()
    for row in shots:
        hashes={row["sha256"],row["original_sha256"]}
        if any(not isinstance(h,str) or len(h)!=64 or any(c not in "0123456789abcdef" for c in h) for h in hashes) or seen&hashes:
            raise ValueError("duplicate or invalid source hash")
        seen.update(hashes)
    return seen

def validate_bundle(bundle,contract):
    if bundle.get("state")!="verified_bundle":
        raise ValueError("missing verified bundle")
    shots=bundle["shots"]
    fps=int(bundle["output"]["fps"])
    counts=[r["frames"] for r in shots]
    validate_plan(shots,counts,fps)
    hashes=verify_distinct(shots)
    cursor=0
    for row in shots:
        if row["start_frame"]!=cursor or row["director_contract"]!=contract:
            raise ValueError("multi-shot contract or timeline mismatch")
        if any(row.get(k,{}).get("verified") is not True for k in ("post_crop_review","joined_review")):
            raise ValueError("missing output shot verification")
        if row.get("source_match",{}).get("director_check",{}).get("verified") is not True:
            raise ValueError("missing source action verification")
        if row.get("pixel_review_required") and row["source_match"].get("pixel_first_proof",{}).get("verified") is not True:
            raise ValueError("missing source pixel verification")
        cursor+=row["frames"]
    if cursor!=bundle["frames"] or cursor!=bundle["output"]["frames"] or abs(cursor/fps-bundle["duration"])>1/fps:
        raise ValueError("multi-shot duration mismatch")
    return hashes

def validate_final_records(scenes):
    seen=set()
    for row in scenes:
        bundle=row.get("multi_shot")
        if bundle:
            if bundle.get("sha256")!=row["sha256"]:
                raise ValueError("bundle hash mismatch")
            hashes=validate_bundle(bundle,row["director_contract"])|{row["sha256"]}
        else:
            hashes={row["sha256"],row.get("original_sha256") or row["sha256"]}
        if seen&hashes:
            raise ValueError("duplicate footage across logical scenes")
        seen.update(hashes)
