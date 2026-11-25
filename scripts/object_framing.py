"""Open-vocabulary object localization and stable, independently verified crop proposals.

No external inference API. A detection is not proof of an action or identity.
Never reject valid footage solely because this optional model is unavailable.
"""
import os
import math
import statistics
import threading
MODEL="IDEA-Research/grounding-dino-tiny"
REVISION="a2bb814dd30d776dcf7e30523b00659f4f141c71"
_LOCK=threading.RLock()
_ENGINE=None
_FAILED=False

def enabled():
    return os.environ.get("PURFFLE_SMART_CROP")=="1"

def detect(frame,subject):
    global _ENGINE,_FAILED
    with _LOCK:
        if _FAILED: raise RuntimeError("Grounding DINO unavailable")
        try:
            import torch
            from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection
            if _ENGINE is None:
                processor=AutoProcessor.from_pretrained(MODEL,revision=REVISION,trust_remote_code=False)
                model=AutoModelForZeroShotObjectDetection.from_pretrained(MODEL,revision=REVISION,
                    trust_remote_code=False,use_safetensors=True).eval()
                _ENGINE=processor,model
            processor,model=_ENGINE
            query=" ".join(str(subject).casefold().split())[:120].rstrip(".")+"."
            inputs=processor(images=frame,text=query,return_tensors="pt")
            with torch.inference_mode():
                output=model(**inputs)
            result=processor.post_process_grounded_object_detection(output,inputs.input_ids,
                threshold=.35,text_threshold=.25,target_sizes=[frame.size[::-1]])[0]
            w,h=frame.size
            out=[]
            for box,score in zip(result["boxes"].tolist(),result["scores"].tolist()):
                x0,y0,x1,y1=box
                coords=[max(0.,min(1.,v)) for v in (x0/w,y0/h,x1/w,y1/h)]
                if all(math.isfinite(v) for v in coords) and coords[2]>coords[0] and coords[3]>coords[1]:
                    out.append({"box":coords,"score":float(score)})
            return sorted(out,key=lambda b:-b["score"])[:6]
        except Exception:
            _ENGINE=None
            _FAILED=True
            raise

def stable_focus(detections,crop_fraction,default=.5):
    """Find a fixed crop retaining most of the strongest box over sampled moments.

    Never animate the camera based on noisy isolated detections. If there is
    insufficient stable evidence, return no proposal and retain existing crop.
    """
    if not 0<crop_fraction<=1: raise ValueError("Invalid crop fraction")
    boxes=[row[0]["box"] for row in detections if row and row[0]["score"]>=.35]
    if len(boxes)<max(2,(len(detections)+1)//2):
        return {"state":"insufficient_detections","focus_x":default,"detected_frames":len(boxes)}
    half=crop_fraction/2
    def clamp(v): return max(half,min(1-half,v))
    candidates=[clamp(default),clamp(statistics.median((b[0]+b[2])/2 for b in boxes))]
    candidates.extend(clamp((b[0]+b[2])/2) for b in boxes)
    def coverage(f,b):
        return max(0.,min(f+half,b[2])-max(f-half,b[0]))/(b[2]-b[0])
    def rank(f):
        scores=[coverage(f,b) for b in boxes]
        return (sum(x>=.8 for x in scores),statistics.mean(scores),-abs(f-default))
    chosen=max(candidates,key=rank)
    base=rank(clamp(default)); best=rank(chosen)
    # Require clear improvement and coverage of at least two frames.
    proposed=best[0]>=2 and best[1]>=base[1]+.10
    return {"state":"proposed" if proposed else "keep_default",
            "focus_x":round(chosen if proposed else clamp(default),5),
            "detected_frames":len(boxes),"sampled_frames":len(detections),
            "default_box_coverage":round(base[1],4),"proposed_box_coverage":round(best[1],4),
            "model":MODEL,"revision":REVISION,"sampled_boxes":boxes}

def propose(path,seconds,subject,source_width,source_height,output_width,output_height,default=.5):
    if not enabled(): return {"state":"disabled","focus_x":default}
    fraction=min(1.,source_height*output_width/(source_width*output_height))
    if fraction>=.98: return {"state":"no_horizontal_crop","focus_x":default}
    try:
        from media_validation import _frame
        times=(.15,max(.2,seconds*.45),max(.3,min(seconds*.85,seconds-.15)))
        frames=[_frame(path,t,640,preserve_aspect=True) for t in times]
        rows=[detect(frame,subject) for frame in frames]
        result=stable_focus(rows,fraction,default)
        result["tracking_shadow"]=track_focus(rows,times,fraction,default)
        return result
    except Exception as exc:
        print("[OBJECT FRAMING UNAVAILABLE]",type(exc).__name__,flush=True)
        return {"state":"unavailable","focus_x":default,"error_type":type(exc).__name__}


def track_focus(detections, times, crop_fraction, default=.5):
    """Conservative sampled horizontal tracking proposal, never a render instruction.

    Associate by nearby box centers and size; abstain on ambiguous identity,
    missing observations or excessive camera speed. Scores are not probabilities.
    """
    def stop(reason):
        return {"state": reason, "keyframes": []}
    if not 0 < crop_fraction <= 1 or len(times) != len(detections) or len(times) < 3:
        return stop("insufficient_samples")
    if any(not math.isfinite(t) for t in times) or any(b <= a for a,b in zip(times,times[1:])):
        return stop("invalid_times")
    half = crop_fraction / 2
    clamp = lambda x: max(half, min(1-half, x))
    center = lambda b: ((b[0]+b[2])/2, (b[1]+b[3])/2)
    area = lambda b: (b[2]-b[0])*(b[3]-b[1])
    boxes = []
    for i,row in enumerate(detections):
        valid = []
        for d in row:
            b = d["box"]
            if (len(b)==4 and all(math.isfinite(v) and 0<=v<=1 for v in b)
                and b[0]<b[2] and b[1]<b[3] and math.isfinite(d["score"]) and d["score"]>=.35):
                valid.append(d)
        if not valid:
            return stop("missing_detection")
        if not boxes:
            valid.sort(key=lambda d: -d["score"])
            if len(valid)>1 and valid[0]["score"]-valid[1]["score"]<.12:
                return stop("ambiguous_identity")
            chosen=valid[0]["box"]
        else:
            prev=boxes[-1]
            cx,cy=center(prev)
            dt=times[i]-times[i-1]
            ranked=[]
            for d in valid:
                b=d["box"]
                x,y=center(b)
                dist=math.hypot(x-cx,y-cy)
                ratio=area(b)/area(prev)
                if dist<=min(.35,.30*dt+.04) and .4<=ratio<=2.5:
                    ranked.append((dist+.06*abs(math.log(ratio)),b))
            ranked.sort(key=lambda v:v[0])
            if not ranked:
                return stop("lost_identity")
            if len(ranked)>1 and ranked[1][0]-ranked[0][0]<.055:
                return stop("ambiguous_identity")
            chosen=ranked[0][1]
        boxes.append(chosen)
    desired=[clamp(center(b)[0]) for b in boxes]
    # Gentle three-point smoothing. A conservative speed cap avoids jump cuts.
    smooth=[desired[0]]+[(desired[i-1]+2*desired[i]+desired[i+1])/4
                         for i in range(1,len(desired)-1)]+[desired[-1]]
    for i in range(1,len(smooth)):
        max_step=.30*(times[i]-times[i-1])
        smooth[i]=max(smooth[i-1]-max_step,min(smooth[i-1]+max_step,smooth[i]))
    smooth=[clamp(x) for x in smooth]
    def coverage(x,b):
        return max(0.,min(x+half,b[2])-max(x-half,b[0]))/(b[2]-b[0])
    fixed=stable_focus(detections,crop_fraction,default)["focus_x"]
    fixed_scores=[coverage(clamp(fixed),b) for b in boxes]
    moving_scores=[coverage(x,b) for x,b in zip(smooth,boxes)]
    improvement=statistics.mean(moving_scores)-statistics.mean(fixed_scores)
    if min(moving_scores)<.8 or improvement<.10:
        return stop("no_safe_improvement")
    return {"state":"shadow_proposal",
            "keyframes":[{"time":round(t,3),"focus_x":round(x,5)} for t,x in zip(times,smooth)],
            "fixed_coverage":round(statistics.mean(fixed_scores),4),
            "tracked_coverage":round(statistics.mean(moving_scores),4),
            "min_tracked_coverage":round(min(moving_scores),4),
            "scope":"sampled box geometry only; dynamic render not enabled"}
