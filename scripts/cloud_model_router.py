"""Shared ordered free-tier model router for Shorts and long documentaries.

No paid-only model, grounding/tool calls, key disclosure or billing changes.
Cloud account billing tier cannot be inferred from an API key; use free-tier keys.
The existing narration, evidence and media validators remain authoritative.
"""
from __future__ import annotations
import json
import os
import time
from types import SimpleNamespace

MODELS=(
    ("gemini","gemini-4-hydrogen"),
    ("groq","openai/gpt-oss-120b"),
    ("gemini","gemini-3.6-flash"),
    ("groq","qwen/qwen3.8-27b"),
    ("gemini","gemini-3.1-flash-lite"),
    ("groq","openai/gpt-oss-20b"),
)
URLS={"gemini":"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
      "groq":"https://api.groq.com/openai/v1/chat/completions"}
KEYS={"gemini":"GEMINI_API_KEY","groq":"GROQ_API_KEY"}

class ModelError(RuntimeError):
    def __init__(self,status,detail=""):
        self.status_code=status
        self.detail=detail
        super().__init__(f"model response unavailable ({status})")

def enabled(env=None):
    return (os.environ if env is None else env).get("PURFFLE_CLOUD_MODEL_ROUTER","0")=="1"

def validate_json(content,schema=None):
    if not isinstance(content,str):
        raise ModelError(422)
    try:
        data=json.loads(content)
    except (TypeError,ValueError):
        raise ModelError(422) from None
    if not isinstance(data,dict):
        raise ModelError(422)
    if schema:
        # jsonschema is installed explicitly in production and audit jobs.
        from jsonschema import Draft202012Validator
        if not Draft202012Validator(schema).is_valid(data):
            raise ModelError(422)
    return data

class Router:
    def __init__(self,env=None,post=None,clock=None):
        env=os.environ if env is None else env
        self.keys={provider:env.get(name,"").strip() for provider,name in KEYS.items()}
        self.local=env.get("PURFFLE_LOCAL_LLM","0")=="1"
        self.post=post
        self.clock=clock or time.monotonic
        self.blocked=set()
        self.cooldown={}
        self.events=[]

    def _event(self,model,status):
        self.events.append({"model":model,"status":status})
        print("[TEXT MODEL]",model,status,flush=True)

    def request(self,provider,model,*,messages,schema=None,max_tokens=4000,temperature=.2,reasoning_effort="low"):
        import requests
        if not self.keys[provider]:
            raise ModelError(401)
        payload={"model":model,"messages":messages,"temperature":float(temperature),
                 "max_tokens":min(8192,max(64,int(max_tokens))),"stream":False}
        if schema:
            fmt={"name":"purffle_reply","schema":schema}
            if provider=="groq":
                fmt["strict"]=True
            payload["response_format"]={"type":"json_schema","json_schema":fmt}
        else:
            payload["response_format"]={"type":"json_object"}
        # Low hidden reasoning helps preserve JSON output space under free TPM.
        if provider=="groq":
            payload["reasoning_effort"]=reasoning_effort if model in ("openai/gpt-oss-120b","openai/gpt-oss-20b") else "low"
        sender=self.post or requests.post
        try:
            response=sender(URLS[provider],headers={"Authorization":"Bearer "+self.keys[provider],
                            "Content-Type":"application/json"},json=payload,timeout=(10,120))
        except (requests.RequestException,OSError,TimeoutError):
            raise ModelError(503) from None
        status=int(response.status_code)
        if status!=200:
            # Inspect but never output account/provider error details.
            detail=""
            if status==429:
                try:
                    body=str(response.json().get("error",{})).lower()
                    if any(x in body for x in ("per day","daily","(tpd)","(rpd)","perday","per_day")):
                        detail="daily"
                except Exception:
                    pass
            raise ModelError(status,detail)
        try:
            choice=response.json()["choices"][0]
            if choice.get("finish_reason")!="stop":
                raise ModelError(422)
            content=choice["message"]["content"]
        except (ValueError,TypeError,KeyError,IndexError):
            raise ModelError(422) from None
        validate_json(content,schema)
        return content

    def complete(self,messages,*,schema=None,max_tokens=4000,temperature=.2):
        for provider,model in MODELS:
            if not self.keys[provider] or provider in self.blocked or model in self.blocked:
                continue
            if self.cooldown.get(model,0)>self.clock():
                continue
            try:
                text=self.request(provider,model,messages=messages,schema=schema,
                                  max_tokens=max_tokens,temperature=temperature)
                self._event(model,"accepted_json")
                return text
            except ModelError as exc:
                status=exc.status_code
                self._event(model,"http_or_json_"+str(status))
                if status==401:
                    self.blocked.add(provider)
                elif status in (403,404,402) or (status==429 and exc.detail=="daily"):
                    self.blocked.add(model)
                elif status==429:
                    self.cooldown[model]=self.clock()+65
                elif status>=500:
                    self.cooldown[model]=self.clock()+30
                # Invalid/truncated JSON or unsupported schema falls through
                # without weakening the schema. No retry of paid-only variants.
        if self.local:
            from local_llm import complete_adaptive
            text=complete_adaptive(messages,schema=schema,max_tokens=max_tokens,
                                   temperature=temperature,prefer="quality")
            validate_json(text,schema)
            self._event("local-qwen","accepted_json")
            return text
        raise RuntimeError("All configured text models unavailable")

    def create(self,**kwargs):
        fmt=kwargs.get("response_format") or {}
        schema=(fmt.get("json_schema") or {}).get("schema")
        text=self.complete(kwargs["messages"],schema=schema,max_tokens=kwargs.get("max_tokens",4000),
                           temperature=kwargs.get("temperature",.2))
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",
                                message=SimpleNamespace(content=text))])

def client(env=None,post=None):
    return SimpleNamespace(chat=SimpleNamespace(completions=Router(env,post)))

def install_short_provider(upstream):
    if not enabled() or "purffle-router" in upstream.PRESETS:
        return
    original=upstream.build_provider
    upstream.PRESETS["purffle-router"]=upstream.Preset("purffle-router","Ordered text models",
        "http://127.0.0.1",(),MODELS[0][1],local=True,schema_mode=True)
    class Provider(upstream.Provider):
        name="purffle-router"
        model=MODELS[0][1]
        def __init__(self):
            self.router=Router()
        def complete(self,system,user,*,schema=None,temperature=.2,max_tokens=4000):
            return self.router.complete([{"role":"system","content":system},
                {"role":"user","content":user}],schema=schema,
                temperature=temperature,max_tokens=max_tokens)
    def build(name,settings,model=""):
        return Provider() if name=="purffle-router" else original(name,settings,model)
    upstream.build_provider=build
