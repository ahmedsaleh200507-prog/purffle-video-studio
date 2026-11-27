"""Optional CPU-only observations. Never authorize unverified stock or identity."""
import math
import os
import threading
import time

_LOCK=threading.Lock()
_COUNTS={"cuts":0,"tracks":0,"index":0}
_LIMITS={"cuts":3,"tracks":3,"index":3}

def reserve(kind):
    if os.getenv("PURFFLE_ADVANCED_VISUALS")!="1":
        return False
    with _LOCK:
        if _COUNTS[kind]>=_LIMITS[kind]:
            return False
        _COUNTS[kind]+=1
        return True

def scene_intervals(path,duration,*,max_seconds=24):
    from scenedetect import detect,ContentDetector
    duration=float(duration)
    if not math.isfinite(duration) or duration<=0:
        raise ValueError("Invalid video duration")
    end=min(duration,float(max_seconds))
    # Explicit string timecode: a plain integer is interpreted as frames.
    spans=detect(str(path),ContentDetector(threshold=27.,min_scene_len=12),
                 end_time=f"{end:.3f}s",start_in_scene=True,show_progress=False)
    return [(max(0.,a.get_seconds()),min(end,z.get_seconds())) for a,z in spans
            if z.get_seconds()>a.get_seconds()]

def cut_observation(path,duration,need,deadline):
    if not reserve("cuts"):
        return {"state":"disabled_or_budget"}
    if deadline-time.monotonic()<35:
        return {"state":"insufficient_time"}
    try:
        # Isolate OpenCV decoding behind a hard timeout.
        import subprocess,sys,json
        result=subprocess.run([sys.executable,__file__,"cuts",str(path),str(duration)],
            capture_output=True,text=True,check=True,timeout=min(15.,deadline-time.monotonic()-15))
        spans=json.loads(result.stdout)
        offsets=[round(a,3) for a,z in spans if z-a>=need+.2]
        return {"state":"observed","spans":spans,"candidate_offsets":offsets[:4],
                "scope":"shot boundaries only; not action verification"}
    except Exception as exc:
        return {"state":"unavailable","error_type":type(exc).__name__}

def track_observations(rows,times):
    import numpy as np
    import supervision as sv
    if len(rows)!=len(times) or len(rows)<3 or len(rows)>24:
        raise ValueError("Invalid sampled tracking input")
    if not all(math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError("Invalid tracking times")
    # The input is already independently corroborated. ByteTrack cannot
    # identify an individual conclusively or restore missing visual evidence.
    tracker=sv.ByteTrack(track_activation_threshold=.35,lost_track_buffer=3,
                         frame_rate=max(1,min(30,round((len(times)-1)/(times[-1]-times[0])))),
                         minimum_consecutive_frames=2)
    tracks={}
    for i,(row,t) in enumerate(zip(rows,times)):
        clean=[]
        for d in row:
            box=d["box"]
            score=float(d["score"])
            if (len(box)==4 and all(math.isfinite(v) and 0<=v<=1 for v in box)
                    and box[0]<box[2] and box[1]<box[3] and .35<=score<=1):
                clean.append((box,score))
        det=sv.Detections(xyxy=np.asarray([b for b,s in clean],dtype=np.float32).reshape(-1,4)*1000,
            confidence=np.asarray([s for b,s in clean],dtype=np.float32),
            class_id=np.zeros(len(clean),dtype=int))
        found=tracker.update_with_detections(det)
        for box,track_id in zip(found.xyxy,found.tracker_id if found.tracker_id is not None else []):
            if track_id is not None and int(track_id)>=0:
                tracks.setdefault(str(int(track_id)),[]).append(
                    {"sample":i,"time":float(t),"box":(box/1000).tolist()})
    return {"state":"observed","tracks":tracks,"sample_count":len(rows),
            "scope":"sampled ByteTrack associations, not identity proof or render instruction"}

def track_review(rows,times):
    if not reserve("tracks"):
        return {"state":"disabled_or_budget"}
    try:
        return track_observations(rows,times)
    except Exception as exc:
        return {"state":"unavailable","error_type":type(exc).__name__}

def tracking_agreement(observation, rows, times, proposal, *, tolerance=.14):
    """ByteTrack is an independent geometry check, never identity proof.

    Do not promote ambiguous tracks. Only compare complete, unique sampled
    paths against an existing conservative crop proposal.
    """
    if proposal.get("state")!="shadow_proposal":
        return {"state":"no_geometry_proposal"}
    if observation.get("state")!="observed":
        return {"state":"unavailable"}
    points=proposal.get("keyframes",[])
    if len(points)!=len(times):
        return {"state":"unavailable"}
    matches=[]
    for key,track in observation.get("tracks",{}).items():
        if [p["sample"] for p in track]!=list(range(len(times))):
            continue
        differences=[]
        for point,entry in zip(points,track):
            b=entry["box"]
            center=(b[0]+b[2])/2
            differences.append(abs(float(point["focus_x"])-center))
        if max(differences)<=tolerance:
            matches.append(key)
    # Sparse samples or a tracker which has not yet confirmed the first
    # observation cannot verify a complete path. Keep static crop in that case.
    return {"state":"agrees" if len(matches)==1 else "inconclusive",
            "matching_tracks":len(matches),"sample_count":len(times),
            "scope":"sampled association agreement, not individual identity"}

def residual_motion(before,after):
    """Estimate local movement after subtracting dominant image translation.

    Only sampled 2-D motion evidence; camera rotation, cuts, occlusion and
    parallax remain possible. Insufficient textured features means abstain.
    """
    import cv2
    import numpy as np
    def gray(im):
        image=np.asarray(im.convert("L"))
        h,w=image.shape
        scale=min(1.,320/max(h,w))
        return cv2.resize(image,(max(1,round(w*scale)),max(1,round(h*scale))))
    a,b=gray(before),gray(after)
    if a.shape!=b.shape:
        return {"state":"incomparable"}
    if np.array_equal(a,b):
        return {"state":"observed","localized_motion":False,"residual_fraction":0.,"tracked_features":0}
    points=cv2.goodFeaturesToTrack(a,maxCorners=160,qualityLevel=.02,minDistance=5)
    if points is None or len(points)<12:
        return {"state":"insufficient_texture"}
    moved,ok,_=cv2.calcOpticalFlowPyrLK(a,b,points,None)
    if moved is None or ok is None:
        return {"state":"insufficient_texture"}
    back,valid,_=cv2.calcOpticalFlowPyrLK(b,a,moved,None)
    if back is None or valid is None:
        return {"state":"insufficient_texture"}
    p,q=points.reshape(-1,2),moved.reshape(-1,2)
    keep=(ok.ravel()==1)&(valid.ravel()==1)&(np.linalg.norm(back.reshape(-1,2)-p,axis=1)<1.5)
    keep &= np.isfinite(q).all(axis=1)
    flow=(q-p)[keep]
    if len(flow)<12 or len(flow)<.5*len(points):
        return {"state":"insufficient_consistent_features"}
    translation=np.median(flow,axis=0)
    residual=np.linalg.norm(flow-translation,axis=1)
    count=int(np.sum(residual>=2.5))
    fraction=count/len(flow)
    return {"state":"observed","localized_motion":count>=4 and fraction>=.08,
            "residual_fraction":round(float(fraction),4),"tracked_features":len(flow),
            "dominant_translation_px":[round(float(x),3) for x in translation],
            "scope":"translation-compensated sampled optical flow, not semantic action"}

def rank_vectors(vectors,query):
    import numpy as np
    import faiss
    x=np.ascontiguousarray(vectors,dtype=np.float32)
    q=np.ascontiguousarray(query,dtype=np.float32).reshape(1,-1)
    if (x.ndim!=2 or not 1<=len(x)<=120 or x.shape[1]!=q.shape[1]
        or not np.isfinite(x).all() or not np.isfinite(q).all()
        or np.any(np.linalg.norm(x,axis=1)<=0) or np.linalg.norm(q)<=0):
        raise ValueError("Invalid embedding index")
    x=x.copy(); q=q.copy()
    faiss.normalize_L2(x); faiss.normalize_L2(q)
    index=faiss.IndexFlatIP(x.shape[1])
    index.add(x)
    scores,ids=index.search(q,len(x))
    return [(int(i),float(s)) for i,s in zip(ids[0],scores[0]) if i>=0]

def rank_library(rows,query):
    """Rank already eligible source metadata, not downloaded video frames."""
    if len(rows)<2 or not reserve("index"):
        return None
    try:
        import torch
        from media_validation import SceneMatcher
        # Never load a large model just to reorder a tiny cached library.
        if SceneMatcher._model is None:
            return None
        with SceneMatcher._lock,torch.inference_mode():
            processor,model=SceneMatcher._processor,SceneMatcher._model
            texts=[query]+[str(r["subject"])+" "+str(r["query"])+" "+str(r["text"])[:400] for r in rows]
            features=[]
            for start in range(0,len(texts),16):
                inputs=processor(text=texts[start:start+16],return_tensors="pt",
                                 padding=True,truncation=True,max_length=77)
                values=model.get_text_features(**inputs)
                if not torch.is_tensor(values):
                    values=values.pooler_output
                features.extend(values.detach().cpu().float().tolist())
        return rank_vectors(features[1:],features[0])
    except Exception:
        return None

if __name__=="__main__":
    import sys,json
    if len(sys.argv)!=4 or sys.argv[1]!="cuts":
        raise SystemExit("cuts PATH DURATION")
    print(json.dumps(scene_intervals(sys.argv[2],float(sys.argv[3]))))
