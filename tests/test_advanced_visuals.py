"""Real library integration tests; synthetic geometry/scene controls are test-only."""
import math
import subprocess
import time
from pathlib import Path
import pytest
from advanced_visuals import rank_vectors,track_observations,scene_intervals,cut_observation

def test_faiss_normalized_exact_ranking():
    result=rank_vectors([[1,0],[0,1],[-1,0]],[4,0])
    assert [i for i,s in result]==[0,1,2]
    assert [s for i,s in result]==pytest.approx([1,0,-1])

def test_faiss_rejects_invalid_vectors():
    for rows in ([[0,0]],[[float("nan"),1]]):
        with pytest.raises(ValueError):
            rank_vectors(rows,[1,0])

def test_bytetrack_two_moving_objects():
    rows=[]
    for i in range(10):
        rows.append([{"box":[.1+i*.005,.2,.25+i*.005,.5],"score":.9},
                     {"box":[.6-i*.005,.3,.75-i*.005,.6],"score":.88}])
    result=track_observations(rows,[i/5 for i in range(len(rows))])
    full=[track for track in result["tracks"].values() if len(track)>=7]
    assert len(full)==2
    for track in full:
        assert max(p["box"][0] for p in track)-min(p["box"][0] for p in track)<.15
    assert "verified" not in result

def test_cut_detector_on_known_hard_cut(tmp_path,monkeypatch):
    path=tmp_path/"two-shots.mp4"
    subprocess.run(["ffmpeg","-hide_banner","-v","error","-y",
        "-f","lavfi","-i","color=red:size=320x240:rate=24:duration=2",
        "-f","lavfi","-i","color=blue:size=320x240:rate=24:duration=2",
        "-filter_complex","[0:v][1:v]concat=n=2:v=1:a=0[out]",
        "-map","[out]","-c:v","libx264","-threads","2",str(path)],check=True,timeout=25)
    spans=scene_intervals(path,4)
    assert len(spans)==2
    assert spans[1][0]==pytest.approx(2,abs=.1)
    monkeypatch.setenv("PURFFLE_ADVANCED_VISUALS","1")
    result=cut_observation(path,4,1,time.monotonic()+60)
    assert result["state"]=="observed"
    assert result["candidate_offsets"]==pytest.approx([0,2],abs=.1)


def test_tracking_consensus_abstains_on_ambiguous_paths():
    from advanced_visuals import tracking_agreement
    times=[0.,1.,2.]
    points=[{"time":t,"focus_x":.4} for t in times]
    track=[{"sample":i,"time":t,"box":[.3,.2,.5,.8]} for i,t in enumerate(times)]
    observation={"state":"observed","tracks":{"1":track}}
    proposal={"state":"shadow_proposal","keyframes":points}
    assert tracking_agreement(observation,[],times,proposal)["state"]=="agrees"
    observation["tracks"]["2"]=track
    assert tracking_agreement(observation,[],times,proposal)["state"]=="inconclusive"

def test_optical_flow_distinguishes_pan_from_local_motion():
    from advanced_visuals import residual_motion
    import cv2
    import numpy as np
    from PIL import Image
    rng=np.random.default_rng(42)
    a=rng.integers(0,256,(240,320),dtype=np.uint8)
    a=cv2.GaussianBlur(a,(3,3),0)
    pan=cv2.warpAffine(a,np.float32([[1,0,4],[0,1,3]]),(320,240),borderMode=cv2.BORDER_REFLECT)
    local=a.copy()
    moved=cv2.warpAffine(a,np.float32([[1,0,8],[0,1,0]]),(320,240),borderMode=cv2.BORDER_REFLECT)
    local[65:175,70:220]=moved[65:175,70:220]
    frozen=residual_motion(Image.fromarray(a),Image.fromarray(a))
    panned=residual_motion(Image.fromarray(a),Image.fromarray(pan))
    changed=residual_motion(Image.fromarray(a),Image.fromarray(local))
    assert frozen["localized_motion"] is False
    assert panned["state"]=="observed" and panned["localized_motion"] is False
    assert changed["state"]=="observed" and changed["localized_motion"] is True

def test_consensus_never_claims_identity_or_action():
    from visual_consensus import summarize
    match={"crop_subject_proof":{"verified":True,"siglip_shadow_review":{"agrees":False},
                                 "visual_language_review":{"models":{"florence":{"state":"observed"}}}}}
    result=summarize(match)
    assert result["state"]=="secondary_disagreement"
    assert result["evidence"]["florence"]=="observed"
    assert result["evidence"]["event"] is None


def test_flow_bridge_uses_actual_pixels_and_only_reports_observed_anchors():
    from advanced_visuals import bridge_observations,anchor_tracks,track_observations
    import numpy as np
    from PIL import Image
    rng=np.random.default_rng(42)
    patch=rng.integers(20,255,(48,32),dtype=np.uint8)
    times=[0.,.6,1.2,1.8,2.4]
    def reader(t):
        a=np.zeros((240,320),dtype=np.uint8)
        x=20+round(t*48)
        a[80:128,x:x+32]=patch
        return Image.fromarray(a)
    rows=[]
    for t in times:
        x=20+round(t*48)
        rows.append([{"box":[x/320,80/240,(x+32)/320,128/240],"score":.92}])
    dense,ts,anchors=bridge_observations(rows,times,reader,time.monotonic()+90)
    assert len(dense)>len(rows)
    assert any(d.get("origin")=="optical_flow" for row in dense for d in row)
    report=anchor_tracks(track_observations(dense,ts),anchors,times)
    assert any(len(v)>=3 for v in report["tracks"].values())
    for track in report["tracks"].values():
        assert all(entry["time"] in times for entry in track)

def test_anchor_tracks_never_reports_flow_only_paths():
    from advanced_visuals import anchor_tracks
    sample=lambda i:{"sample":i,"time":i*.1,"box":[.1,.2,.3,.4]}
    report={"state":"observed","sample_count":9,
            "tracks":{"flow":[sample(1),sample(2)],"one":[sample(0),sample(1)],
                      "two":[sample(0),sample(1),sample(4)]}}
    result=anchor_tracks(report,{0:0,4:1,8:2},[0.,.4,.8])
    assert set(result["tracks"])=={"two"}
    assert [r["sample"] for r in result["tracks"]["two"]]==[0,1]

def test_bridge_stops_if_scene_time_budget_is_exhausted():
    from advanced_visuals import bridge_observations
    def reader(t):
        pytest.fail("Must not decode frames after deadline")
    assert bridge_observations([[],[],[]],[0.,.6,1.2],reader,time.monotonic()) is None
