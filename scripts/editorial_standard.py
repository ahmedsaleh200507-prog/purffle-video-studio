"""Shared Purffle editorial contract. No prediction of views or truth from scores."""
import os
import re
import math

VERSION="purffle_four_phase_v3"
PHASES=("hook","curiosity","development","payoff")
CORE_BRIEF=(
    "Tell one coherent story that answers the EXACT requested topic. "
    "HOOK: start immediately with a concrete, true, surprising consequence, "
    "contrast, observable action, or specific question. Never invent shock or statistics. "
    "CURIOSITY: give a useful fact early and establish the question that remains. "
    "DEVELOPMENT: each beat advances the answer with new, connected information; "
    "prefer concrete examples, understandable cause and effect, and natural spoken language. "
    "PAYOFF: resolve the promise, do not end with an unrelated fact, CTA or fake cliffhanger. "
    "Use accurate native-language speech, filmable real visuals and honest illustrative B-roll. "
    "No invented quotes, fictional documentary events, repetition, padding or misleading titles."
)

def enabled():
    return os.getenv("PURFFLE_EDITORIAL_STANDARD")=="1"

def word_tokens(s):
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)?",str(s).casefold())

def chapter_phase(index):
    if not 1<=index<=14:
        raise ValueError("Expected chapter 1 through 14")
    return "hook" if index==1 else "curiosity" if index<=3 else "development" if index<=12 else "payoff"

def long_brief():
    return CORE_BRIEF + (
        " Across the 14 chapters: chapter 1 opens with a strong cold open, "
        "chapters 2–3 establish the stakes and useful context, chapters 4–12 "
        "develop new evidence and mechanisms in logical order, chapters 13–14 "
        "resolve the question and explain its significance. Each chapter must add "
        "something new, with a natural transition, not restart the story."
    )

def chapter_context(outline,offset,previous):
    # Preserve the whole story arc on paired and single-chapter retries.
    arc=" | ".join(f"{i+1} [{chapter_phase(i+1)}] {row['title']}" for i,row in enumerate(outline))
    prior=" ".join(word_tokens(previous)[-35:]) if previous else "(start of film)"
    return f"Whole film outline: {arc}. Prior narration ending: {prior}. Current section starts at {offset+1}."

def audit_structure(texts,language,*,mode):
    from retention_storyboard import _EN_INTROS,_DE_INTROS,_BAD_ENDINGS
    words=[word_tokens(x) for x in texts]
    if not words or any(not x for x in words):
        raise RuntimeError("editorial_empty_narration")
    first=" ".join(words[0])
    intros=_DE_INTROS if language=="de" else _EN_INTROS
    if any(first.startswith(" ".join(word_tokens(x))) for x in intros):
        raise RuntimeError("editorial_generic_opening")
    all_text=" ".join(" ".join(x) for x in words)
    if any(" ".join(word_tokens(x)) in all_text for x in _BAD_ENDINGS):
        raise RuntimeError("editorial_generic_engagement_prompt")
    if mode=="short" and sum(map(len,words))<32:
        raise RuntimeError("editorial_short_narration_under_32_words")
    # Reject repeated substantive sentences even across nonadjacent scenes.
    seen=set()
    for text in texts:
        for sentence in re.split(r"(?<=[.!?])\s+",text):
            tok=word_tokens(sentence)
            if len(tok)>=8:
                key=tuple(tok)
                if key in seen:
                    raise RuntimeError("editorial_repeated_sentence")
                seen.add(key)
    return {"version":VERSION,"state":"structure_screened","words":sum(map(len,words)),
            "scope":"structure only; factual and visual checks remain separate"}

def final_timing(captions,duration,*,mode):
    from output_qa import caption_intervals
    duration=float(duration)
    if not math.isfinite(duration) or duration<=0:
        raise RuntimeError("editorial_invalid_duration")
    rows=caption_intervals(captions,duration)
    if rows[0][0]>.9:
        raise RuntimeError("editorial_late_first_caption")
    # Sidecar timing for long, word captions for Shorts. Not ASR/visible OCR.
    if duration-rows[-1][1]>(1.5 if mode=="short" else 2.5):
        raise RuntimeError("editorial_missing_final_payoff_caption")
    return {"state":"timing_screened","version":VERSION,
            "first_caption_seconds":rows[0][0],"last_caption_seconds":rows[-1][1],
            "duration":duration,"scope":"caption timeline; not viewer retention or semantic truth"}

def review_long(topic,language,chapters,client):
    """One separate editor request over the entire story, not a fact-check oracle."""
    from long_generic import _retried_json
    keys=("answers_topic","specific_opening","early_value","coherent_progression","complete_payoff")
    schema={"type":"object","properties":{**{key:{"type":"boolean"} for key in keys},
        "reason":{"type":"string"}},"required":[*keys,"reason"],"additionalProperties":False}
    def validate(data):
        if not isinstance(data,dict) or set(data)!=set(keys)|{"reason"} or any(type(data[k]) is not bool for k in keys):
            raise ValueError("editorial_verdict_schema")
        return data
    import time
    prompt=("Act as a separate documentary EDITOR, not the writer. Judge only narrative quality, "
        "not popularity or factual proof. "+long_brief()+"\nExact topic: "+topic+
        "\nLanguage: "+language+"\nFull script:\n"+"\n".join(
            f"{i+1}. {row['title']}\n{row['narration']}" for i,row in enumerate(chapters))+
        "\nReturn the requested boolean verdicts and short reason. Be strict about topic drift, repetition and missing conclusion.")
    verdict=_retried_json(client,prompt,schema,"long_editorial_review",validate,sleep=time.sleep,max_tokens=1800)
    if not all(verdict[k] for k in keys):
        raise RuntimeError("long_editorial_rejected: "+",".join(k for k in keys if not verdict[k]))
    return {"version":VERSION,"state":"model_screened_editorial",**{k:verdict[k] for k in keys},
            "scope":"editorial model judgment; not source-level factual verification or retention measurement"}
