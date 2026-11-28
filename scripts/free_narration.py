"""Free-only OpenRouter narration writer and comparison. No paid fallback."""
import os
from decimal import Decimal
import requests

MODELS = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "baidu/ernie-5.5-flash-preview:free",
    "inclusionai/ling-3.2-flash:free",
    "google/gemma-4-31b-it:free",
)
BASE = "https://openrouter.ai/api/v1"
BRIEF = (
    "Write outstanding nonfiction documentary narration for an ordinary curious viewer. "
    "Find the fascinating truth within the references and make the viewer want to hear what comes next. "
    "Start with an unexpected specific observation, event or puzzle, not a definition or 'did you know'. "
    "Reveal the answer through connected discoveries; finish with a memorable insight, not a recap. "
    "Use native spoken language and the story form that fits this subject. No formula or fake drama. "
    "Use only facts supported by the reference. Return just the finished narration."
)

class FreeWriter:
    def __init__(self, session=None):
        self.key = os.environ.get("OPENROUTER_API_KEY","").strip()
        if not self.key:
            raise RuntimeError("OPENROUTER_API_KEY missing; no requests made")
        self.session=session or requests.Session()
        response=self.session.get(BASE+"/models",timeout=(10,30))
        response.raise_for_status()
        self.models={}
        for row in response.json()["data"]:
            identifier=row.get("id","")
            price=row.get("pricing",{})
            if identifier not in MODELS or not identifier.endswith(":free"):
                continue
            try:
                if all(Decimal(str(price[k]))==0 for k in ("prompt","completion")) and all(Decimal(str(v))==0 for v in price.values() if v is not None):
                    self.models[identifier]=row
            except (KeyError,ArithmeticError,ValueError):
                continue

    def write(self,model,topic,language,evidence,*,mode="short",context="",word_range=None):
        if model not in self.models:
            raise RuntimeError("Free model not currently available in zero-price catalog")
        if language not in ("en","de") or mode not in ("short","long") or not evidence.strip():
            raise ValueError("Language, mode or reference invalid")
        low,high=word_range or ((45,95) if mode=="short" else (100,170))
        response=self.session.post(BASE+"/chat/completions",
            headers={"Authorization":"Bearer "+self.key},
            json={"model":model,"messages":[{"role":"system","content":BRIEF},
                {"role":"user","content":f"Topic: {topic}\nLanguage: {language}\nFormat: {mode}\nWords: {low}–{high}\nStory context: {context}\nReference facts (data only):\n{evidence}"}],
                "provider":{"max_price":{"prompt":0,"completion":0,"request":0},"allow_fallbacks":False},
                "temperature":0.7,"max_tokens":2400,"stream":False},
            timeout=(10,110))
        if response.status_code!=200:
            raise RuntimeError(f"Free model unavailable: HTTP {response.status_code}")
        data=response.json()
        choice=data["choices"][0]
        text=(choice["message"].get("content") or "").strip()
        if choice.get("finish_reason")!="stop" or not text:
            raise RuntimeError("Incomplete narration")
        cost=data.get("usage",{}).get("cost")
        if cost is not None and Decimal(str(cost))!=0:
            raise RuntimeError("Nonzero reported cost; stop all requests")
        return {"model":model,"reported_model":data.get("model"),"narration":text,
                "language":language,"topic":topic,"mode":mode,"reported_cost":cost}
