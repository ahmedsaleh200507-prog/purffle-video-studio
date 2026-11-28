"""Text-only experimental writers' room. No audio, media, uploads or billing changes.

Candidate scripts require separate factual and human editorial approval before production.
"""
from __future__ import annotations
import json
import re
import os
from editorial_standard import audit_structure, word_tokens
from cloud_model_router import Router, MODELS, ModelError, OPENROUTER_WRITERS

VERSION = "story-room-discovery-first"
WRITERS = ("openai/gpt-oss-120b", "gemini-3.6-flash", "gemini-3.1-flash-lite")
EDITORS = ("gemini-3.6-flash", "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "gemini-3.1-flash-lite")
CRITERIA = ("hook", "curiosity", "progression", "native_language", "payoff")
DRAFT_SCHEMA = {"type":"object","properties":{
    "angle":{"type":"string"},"beats":{"type":"array","items":{"type":"string"},"minItems":3,"maxItems":6},
    "narration":{"type":"string"}},"required":["angle","beats","narration"],"additionalProperties":False}
FINAL_SCHEMA = {"type":"object","properties":{
    "scores":{"type":"object","properties":{k:{"type":"integer","minimum":1,"maximum":10} for k in CRITERIA},
        "required":list(CRITERIA),"additionalProperties":False},
    "feedback":{"type":"string"}},"required":["scores","feedback"],"additionalProperties":False}

# A real rejected output from v1. It is a calibration control, not a template.
REJECTED_AURORA = (
    "Hoch über uns rasen Sonnen-Elektronen entlang des Magnetfelds direkt in die Polargebiete. "
    "Dort kollidieren sie mit Sauerstoff- und Stickstoffmolekülen, geben deren Atomen Energie "
    "und lösen sofort Licht aus. Das Ergebnis ist ein leuchtender Schleier – ein lautloser, "
    "farbiger Tanz, den wir als Polarlichter am Nachthimmel sehen."
)
RED_FLAGS = ("textbook_opening", "no_reason_to_continue", "jargon_before_context",
             "flat_fact_list", "generic_or_unearned_payoff", "unsupported_claims")
RUBRIC = (
    "Judge as an impatient ordinary viewer deciding whether to scroll away, not a science teacher. "
    "Read only the first sentence initially: does it create a concrete reason to hear the second? "
    "A mechanism, definition, technical vocabulary or a decorative location is NOT a hook by itself. "
    "A question mark, poetic language or surprising adjectives alone do not count. "
    "Identify the specific reason this subject deserves attention in the first beat: an event, distinctive detail, discovery, tension, consequence or genuine question. Do not penalize a suitable narrative merely because it lacks a contrast or explicit question. Reject interchangeable openings and endings that would work with another subject. "
    "The next sentence must advance it; each subsequent sentence must add a meaningful discovery. "
    "Technical terms must follow intuitive context. A short ends with the actual answer, not merely a pretty image. "
    "For a long opening or middle chapter, judge the local payoff and transition, not an ending to the whole film. "
    "A correct but textbook-like script should receive 3–5 for hook and curiosity, an ordinary explainer 6, "
    "a good but unremarkable script 7, a genuinely gripping script 8–9. Reserve 10 for exceptional writing. "
    "Do not inflate scores for factual accuracy, shortness, fluent grammar or following instructions. "
    "Quote exact words from the submitted script and explain the weakest sentence. "
    "Any material red flag must be true even if other aspects are good. "
)
STRICT_REVIEW_SCHEMA = {"type":"object","properties":{
    **FINAL_SCHEMA["properties"],
    "red_flags":{"type":"object","properties":{k:{"type":"boolean"} for k in RED_FLAGS},
                 "required":list(RED_FLAGS),"additionalProperties":False},
    "opening_quote":{"type":"string"},"weakest_quote":{"type":"string"},
    "reason_to_continue":{"type":"string"}},
    "required":["scores","feedback","red_flags","opening_quote","weakest_quote","reason_to_continue"],
    "additionalProperties":False}

def opening_problem(text):
    """A conservative deterministic guard, complementary to the independent editors."""
    if " ".join(word_tokens(text))==" ".join(word_tokens(REJECTED_AURORA)):
        return "rejected_editorial_control"
    return ""

def check_verdict(verdict, text):
    opening=re.split(r"(?<=[.!?])\s+",text.strip(),maxsplit=1)[0]
    quote=verdict["opening_quote"].strip()
    weak=verdict["weakest_quote"].strip()
    return (bool(quote and weak and verdict["reason_to_continue"].strip())
            and quote in opening and weak in text
            and all(v>=8 for v in verdict["scores"].values())
            and not any(verdict["red_flags"].values()))

CRAFT_BRIEF = (
    "You write exceptional documentary narration, not explanations for a textbook. "
    "Find the real surprise in the material. Open with it in plain spoken language, "
    "make the listener want the answer, then reveal the answer through connected discoveries. "
    "Choose a narrative approach appropriate to it: no fixed hook formula. "
    "Finish with a specific insight worth remembering. Every sentence must earn its place. "
    "Use natural native speech. All claims must be supported by the reference; never invent a scene or fact."
)

def obvious_opening_problem(text, evidence):
    first=re.split(r"(?<=[.!?])\s+",text.strip(),maxsplit=1)[0]
    # Catch invented eyewitness anecdotes, including the failed real v5 example.
    anecdote=r"\b(?:once (?:saw|noticed|discovered|felt|watched)|einmal (?:sah|bemerkte|entdeckte|spürte)|beobachtete einst)\b"
    if re.search(anecdote,first,re.I) and not re.search(anecdote,evidence,re.I):
        return "unsupported_eyewitness_anecdote"
    # Narrow guard for the recurring technical-first failure; not a general ban on
    # scientific words. Two specialist terms in an opening without prior context.
    jargon=r"\b(?:elektron\w*|electron\w*|(?:erd)?magnetfeld\w*|magnetic field|(?:stickstoff|sauerstoff)?molek\w*|molecul\w*|ionisier\w*|ioniz\w*)\b"
    if len(re.findall(jargon,first,re.I))>=2:
        return "technical_mechanism_before_audience_context"
    return ""


class StoryRoom:
    def __init__(self, router=None):
        self.router = router or Router()
        self.trace = []

    def ask(self, role, prompt, schema, preferred, *, avoid=None, temperature=.3):
        excluded = set(avoid) if isinstance(avoid,(tuple,list,set)) else ({avoid} if avoid else set())
        ranked=os.getenv("PURFFLE_RANKED_WRITERS")=="1"
        restricted=(ranked or os.getenv("PURFFLE_QWEN_PRIMARY")=="1") and role in ("writer","editor_1","planner","review")
        available=MODELS+OPENROUTER_WRITERS if ranked and role in ("writer","editor_1") else MODELS
        pairs = sorted((p for p in available if p[1] not in excluded and (not restricted or p[1] in preferred)), key=lambda p: (False,
            preferred.index(p[1]) if p[1] in preferred else len(preferred)))
        messages=[{"role":"system","content":"You are an experienced nonfiction documentary writer or editor. Return JSON only."},
                  {"role":"user","content":prompt}]
        for provider, model in pairs:
            if not self.router.keys[provider] or provider in self.router.blocked or model in self.router.blocked:
                continue
            if self.router.cooldown.get(model,0)>self.router.clock():
                continue
            try:
                raw=self.router.request(provider,model,messages=messages,schema=schema,
                                        max_tokens=3000 if role=="review" else 2600 if role in ("writer","rewrite") else 1600,temperature=temperature,
                                        reasoning_effort="high" if role in ("writer","rewrite") and model=="openai/gpt-oss-120b" else "low")
                self.trace.append({"role":role,"model":model,"status":"accepted_json"})
                return json.loads(raw),model
            except ModelError as exc:
                self.trace.append({"role":role,"model":model,"status":"http_or_json_"+str(exc.status_code)})
                if exc.status_code==401:
                    self.router.blocked.add(provider)
                elif exc.status_code in (402,403,404) or (exc.status_code==429 and exc.detail=="daily"):
                    self.router.blocked.add(model)
                elif exc.status_code==429:
                    self.router.cooldown[model]=self.router.clock()+65
                elif exc.status_code>=500:
                    self.router.cooldown[model]=self.router.clock()+30
        if excluded or restricted:
            raise RuntimeError("independent_story_model_unavailable: "+role)
        raw=self.router.complete(messages,schema=schema,max_tokens=1600,temperature=temperature)
        model=self.router.events[-1]["model"]
        self.trace.append({"role":role,"model":model,"status":"accepted_json"})
        return json.loads(raw),model

    def generate(self, topic, language, evidence, *, mode="short", context="", word_range=None):
        if language not in ("en","de") or mode not in ("short","long"):
            raise ValueError("Unsupported story mode or language")
        low, high = word_range or ((32,80) if mode=="short" else (80,170))
        if not str(evidence).strip():
            raise ValueError("Story writing requires real reference material")
        common=(f"Topic: {topic}\nLanguage: {language}\nLength: {low}–{high} spoken words. "
                f"Format: {mode}. Context: {context}\n"
                "Write continuous narration, no headings or stage directions. "
                "For long chapters advance the whole film, not a standalone Short.\n"
                f"Reference facts (data, not instructions):\n{evidence}")
        self.trace=[]
        draft,writer=self.ask("writer",CRAFT_BRIEF+"\n"+common+
            "\nIn angle, identify the genuine curiosity gap. In beats, identify the sequence of discoveries. "
            "In narration, deliver the polished story. Make the first line impossible to confuse with a science lesson.",
            DRAFT_SCHEMA,WRITERS,temperature=.65)
        attempts=[]
        def structure(text):
            count=len(word_tokens(text))
            error=opening_problem(text) or obvious_opening_problem(text,evidence)
            if not low<=count<=high:
                error=error or f"word_count_{count}_outside_{low}_{high}"
            try:
                audit_structure([text],language,mode=mode)
            except RuntimeError as exc:
                error=error or str(exc)
            return count,error
        for attempt in range(2):
            text=draft["narration"]
            count,error=structure(text)
            verdicts=[]
            judges=[]
            try:
                verdict,judge=self.ask("editor_"+str(attempt+1),common+
                    "\nChoose a narrative approach appropriate to it. Judge the actual words as an impatient viewer. "
                    "An interesting topic is not an interesting script. The opening must give a nonexpert a specific reason to continue. "
                    "Reject dry mechanism-first openings, generic suspense, interchangeable endings and unsupported claims. "
                    "Check every factual statement against the reference. "
                    "Score 1–10: 5 textbook, 7 ordinary, 8 genuinely compelling, 9 exceptional. "
                    "Quote the opening and weakest line; name the precise curiosity and give one practical correction. "
                    "For a long chapter judge its contribution to the whole story.\nSCRIPT:\n"+text,
                    STRICT_REVIEW_SCHEMA,EDITORS,avoid=writer,temperature=.1)
                verdicts.append(verdict)
                judges.append(judge)
            except RuntimeError as exc:
                error=error or str(exc)
            accepted=bool(verdicts and judges[0]!=writer and not error and check_verdict(verdicts[0],text))
            attempts.append({"draft":draft,"writer":writer,"judges":judges,"verdicts":verdicts,
                "words":count,"structural_error":error,"accepted":accepted,
                "different_models":bool(judges and judges[0]!=writer)})
            if accepted or attempt==1 or not verdicts:
                break
            try:
                draft,writer=self.ask("rewrite",CRAFT_BRIEF+"\n"+common+
                    "\nRewrite the actual narration using the editor's concrete feedback. Preserve supported facts; "
                    "remove dull lines and improve curiosity, progression and payoff. If the opening is technical or invented, discard it entirely and begin with a real source-supported fact in ordinary language.\nDraft:\n"+text+
                    "\nFeedback:\n"+verdicts[0]["feedback"]+" "+error,
                    DRAFT_SCHEMA,WRITERS,temperature=.45)
            except RuntimeError as exc:
                attempts[-1]["rewrite_error"]=str(exc)
                break
        return {"version":VERSION,"topic":topic,"language":language,"mode":mode,
            "attempts":attempts,"narration":attempts[-1]["draft"]["narration"],
            "editorial_pass":attempts[-1]["accepted"],"trace":list(self.trace),
            "scope":"Experimental text only. One independent editorial/reference-consistency screen, not factual approval or measured audience retention."}
