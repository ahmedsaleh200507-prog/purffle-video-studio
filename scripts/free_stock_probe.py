"""Read-only stock discovery proof, no downloads, no paid services.
Provider credentials must be supplied only by the owner-confirmed workflow.
Metadata hints are not verified video content or proof of ownership.
"""
import json
import os
from dataclasses import dataclass,field
from pathlib import Path

TOPICS=("volcano lava eruption","octopus underwater camouflage","autumn forest seasons","mangrove forest coastal roots")
PROVIDERS=("pexels","pixabay")

@dataclass
class Candidate:
    source:str
    id:str
    kind:str
    url:str
    width:int
    height:int
    duration:float=0
    query:str=""
    rank:int=0
    text:str=""
    credit:str=""
    extra:dict=field(default_factory=dict)

def summarize(items):
    # Identical quality policy used by production, with no assumption that
    # provider-reported dimensions or durations are measured or reliable.
    eligible=[i for i in items if min(i.width,i.height)>=720 and max(1080/i.width,1920/i.height)<=1.2001]
    return {"candidates":len(items),"portrait_quality_hints":len(eligible),
            "short_shot_hints":sum(i.duration>=2.1 for i in eligible),
            "eight_second_hints":sum(i.duration>=8.1 for i in eligible),
            "unknown_duration":sum(i.duration<=0 for i in eligible)}

def main():
    from video_sources import ProviderRegistry
    reg=ProviderRegistry(MediaItem=Candidate)
    report={"scope":"Search metadata only; no download, semantic verification or actual account billing proof.","providers":{}}
    configured=0
    verified=0
    for provider in PROVIDERS:
        flag=os.environ.get("PURFFLE_"+provider.upper()+"_FREE_CONFIRMED")=="1"
        key=os.environ.get(provider.upper()+"_API_KEY")
        result={"state":"not_confirmed" if not flag else "missing_key" if not key else "configured","queries":[]}
        if flag and key:
            configured+=1
            for query in TOPICS:
                before=len(reg.events)
                items=reg.search(provider,query)
                event=reg.events[before:]
                status=event[-1]["status"] if event else "no_event"
                result["queries"].append({"query":query,"status":status,**summarize(items)})
                if provider in reg._circuit:
                    break
            result["state"]="reachable" if any(x["status"] in ("ok","empty") for x in result["queries"]) else "api_unavailable"
            verified+=int(result["state"]=="reachable")
        report["providers"][provider]=result
    report["configured"]=configured
    report["reachable"]=verified
    Path("free-stock-report.json").write_text(json.dumps(report,indent=2))
    print("FREE STOCK SUMMARY",json.dumps(report),flush=True)
    return 0 if configured==2 and verified==2 else 1

if __name__=="__main__":
    raise SystemExit(main())
