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
