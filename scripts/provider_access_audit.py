"""Read-only provider catalog diagnostics. No inference, no billing changes.
A listed model is not proof of free quota or generation access.
Never emit keys, raw HTTP responses or other account data.
"""
import json
import os
from pathlib import Path

TARGETS={
    "gemini":("gemini-4-hydrogen","gemini-3.8-flash","gemini-3.6-flash",
              "gemini-3.5-flash-lite","gemini-3.1-flash-lite","gemma-4-31b-it","gemma-4-26b-a4b-it"),
    "groq":("qwen/qwen3.8-27b","openai/gpt-oss-120b","openai/gpt-oss-20b"),
    "openrouter":("nvidia/nemotron-3-ultra-550b-a55b:free","baidu/ernie-5.5-flash-preview:free",
                  "google/gemma-4-31b-it:free","google/gemma-4-26b-a4b-it:free"),
}
KEYS={"gemini":"GEMINI_API_KEY","groq":"GROQ_API_KEY","openrouter":"OPENROUTER_API_KEY"}
URLS={"gemini":"https://generativelanguage.googleapis.com/v1beta/models",
      "groq":"https://api.groq.com/openai/v1/models","openrouter":"https://openrouter.ai/api/v1/models"}

def classify_status(status):
    return {400:"invalid_request",401:"invalid_credentials",403:"permission_denied",
            404:"endpoint_not_found",429:"rate_limited",503:"provider_unavailable"}.get(status,"http_error")

def scan(provider,env,get=None):
    import requests
    targets=TARGETS[provider]
    key=env.get(KEYS[provider],"").strip()
    if not key:
        return {"provider":provider,"status":"key_missing","models":[]}
    get=get or requests.get
    headers={"x-goog-api-key":key} if provider=="gemini" else {"Authorization":"Bearer "+key}
    found={}
    token=None
    seen=set()
    try:
        for _ in range(10):
            params={}
            if provider=="gemini":
                params={"pageSize":100}
                if token:
                    params["pageToken"]=token
            response=get(URLS[provider],headers=headers,params=params,timeout=(10,30),allow_redirects=False)
            if response.status_code!=200:
                return {"provider":provider,"status":classify_status(response.status_code),"http":response.status_code,"models":[]}
            data=response.json()
            entries=data.get("models" if provider=="gemini" else "data")
            if not isinstance(entries,list):
                raise ValueError("catalog shape")
            for entry in entries:
                if not isinstance(entry,dict):
                    continue
                name=entry.get("name" if provider=="gemini" else "id","")
                if provider=="gemini" and isinstance(name,str):
                    name=name.removeprefix("models/")
                if name not in targets:
                    continue
                row={"id":name,"listed":True}
                if provider=="gemini":
                    methods=entry.get("supportedGenerationMethods")
                    row["generate_content_supported"]="generateContent" in methods if isinstance(methods,list) else None
                if provider=="openrouter":
                    price=entry.get("pricing") or {}
                    required=("prompt","completion")
                    fields=required+("image","request","video","audio")
                    try:
                        row["catalog_zero_pricing"]=all(k in price for k in required) and all(float(price[k])==0 for k in fields if k in price)
                    except (ValueError,TypeError):
                        row["catalog_zero_pricing"]=None
                found[name]=row
            token=data.get("nextPageToken") if provider=="gemini" else None
            if not token:
                break
            if not isinstance(token,str) or token in seen:
                raise ValueError("pagination")
            seen.add(token)
        else:
            return {"provider":provider,"status":"catalog_incomplete","models":list(found.values())}
    except (requests.RequestException,OSError):
        return {"provider":provider,"status":"network_error","models":[]}
    except (ValueError,TypeError,KeyError):
        return {"provider":provider,"status":"invalid_catalog","models":[]}
    return {"provider":provider,"status":"catalog_read","models":[found.get(m,{"id":m,"listed":False}) for m in targets],
            "scope":"catalog metadata only; generation availability, account billing and quota not verified"}

def main():
    rows=[scan(p,os.environ) for p in TARGETS]
    root=Path("provider-access-audit")
    root.mkdir(exist_ok=True)
    (root/"report.json").write_text(json.dumps(rows,indent=2))
    for row in rows:
        print("PROVIDER ACCESS",json.dumps(row),flush=True)
    return 0 if all(r["status"]=="catalog_read" for r in rows) else 1

if __name__=="__main__":
    raise SystemExit(main())
