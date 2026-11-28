"""Three distinct CC0 water shots, one 9-second Full-HD silent scene."""
import json
import tempfile
from pathlib import Path
from media_validation import SceneMatcher,VideoDownloader,_frame
from visual_ensemble_proof import source,rank
from siglip_review import score
from event_theme_review import motion_pair
from multi_shot import assemble,frame_plan,digest

def main():
    import torch
    torch.set_num_threads(2)
    out=Path("multi-shot-proof")
    out.mkdir(exist_ok=True)
    matcher=SceneMatcher()
    cases=[
        ("coast","rugged-ocean-coast","Ocean waves moving against a rocky coast.","A calm ocean without waves.",.56),
        ("river","autumn-leaves-in-river-water","Autumn leaves floating in river water.","Dry leaves on the ground without water.",2.),
        ("waterfall","leaves-dancing-before-a-waterfall","Foliage in front of a waterfall.","Dry rock without falling water.",2.),
    ]
    def review(path,length,row,start=0.,portrait=True):
        times=[start+length*f for f in (.15,.45,.75)]
        frames=[_frame(path,t,448,preserve_aspect=True) for t in times]
        adjacent=[_frame(path,t+.15,448,preserve_aspect=True) for t in times]
        queries=row["queries"]
        a=matcher._similarities(frames,queries)
        b=score(frames,queries)
        moving=sum(motion_pair(x,y)["localized_change_observed"] for x,y in zip(frames,adjacent))>=2
        return {"verified":rank(a,0) and rank(b,0) and moving,
                "clip":a,"siglip":b,"motion":moving,"sample_times":times}
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        downloader=VideoDownloader(root/"cache",max_bytes=180*1024*1024,total_timeout=90)
        shots=[]
        counts=frame_plan(9.)
        for (name,identifier,positive,negative,start),n in zip(cases,counts):
            queries=[positive,negative,"A campfire burning."]
            path,meta=source((name,"freenaturestock_video_catalog.json",identifier,*queries),root,downloader)
            sha=digest(path)
            row={"path":str(path),"id":identifier,"source":"freenaturestock-video",
                 "license":{"id":meta["license"],"url":meta["license_url"],"source_page":meta["source"]},
                 "sha256":sha,"start":start,"focus":.5,"queries":queries}
            approval=review(path,n/30,row,start,False)
            row["approval"]={**approval,"start":start,"seconds":n/30,"sha256":sha}
            print("MULTI SHOT SOURCE",name,json.dumps(row["approval"]),flush=True)
            shots.append(row)
        result=assemble(shots,counts,out/"water-montage.mp4",review=review)
        (out/"report.json").write_text(json.dumps(result,indent=2))
        print("MULTI SHOT SUMMARY",json.dumps({"shots":len(result["shots"]),"frames":result["frames"],
              "duration":result["duration"],"output":result["output"],"state":result["state"]}),flush=True)
    return 0
if __name__=="__main__":
    raise SystemExit(main())
