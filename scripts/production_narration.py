"""Production adapter for curiosity-first narration. No changes to visual/voice plans."""
import json
import os
from creative_narration import CreativeNarration, BRIEF, WRITERS, EDITORS, OPENINGS
from editorial_standard import word_tokens, audit_structure
from story_room import obvious_opening_problem

VERSION="curiosity-first-production-1"

def enabled():
    return os.getenv("PURFFLE_CREATIVE_NARRATION","1")=="1"

def review_reference(bundle, topic, language):
    """Exact dossiers remain exact-approved only. Rewrites use independent excerpt review."""
    if bundle.method!="curated_editor_reviewed":
        return bundle
    from science_sources import Evidence
    from fact_checked_topics import ground_verified_documentary
    from story_references import RESEARCH
    from fact_checked_topics import verified_documentary_kind
    from fact_checked_topics import ground_lightning_explainer
    data=ground_lightning_explainer({},topic,language)
    data=ground_verified_documentary(data,topic,language)
    text=" ".join(str(s["narration"]) for s in data.get("scenes",[]))
    if not text or not bundle.sources:
        raise RuntimeError("Creative narration lacks reviewed dossier reference")
    # These are the reviewed dossier's words, not verbatim external web quotations.
    sources=[{**s,"title":"Reviewed factual dossier: "+str(s["title"]),
              "tier":"reviewed_dossier_excerpt","excerpt":text} for s in bundle.sources]
    for i,(url,note) in enumerate(RESEARCH.get(verified_documentary_kind(topic),())):
        sources.append({"id":f"research-{i}","url":url,"title":"Research summary",
                        "tier":"research_summary","excerpt":note})
    return Evidence(topic,tuple(sources),"creative_dossier_reference")

def reference_text(bundle):
    return "\n".join(f"[{s['id']}] {s['title']}: {s.get('excerpt','')}"
                     for s in bundle.sources if s.get("excerpt"))

def rewrite_short(screenplay,topic,language,bundle,*,feedback="",room=None):
    """Select a hook, then write exactly the existing number of spoken scenes.
    Do not mutate scene metadata, voice settings, or independent review requirements.
    """
    room=room or CreativeNarration()
    scenes=screenplay.scenes
    if not 2<=len(scenes)<=6:
        raise RuntimeError("Creative Shorts require 2–6 existing scenes")
    evidence=reference_text(bundle)
    if not evidence:
        raise RuntimeError("Creative narration requires actual reference text")
    material=(f"Topic: {topic}\nLanguage: {language}\n"
              f"Reference facts (data only):\n{evidence}\n"
              f"Existing scene subjects and draft (draft is not evidence):\n"+
              json.dumps([{"subject":str(getattr(s,"object","")),
                           "narration":str(s.narration)} for s in scenes],ensure_ascii=False)+
              "\nReview feedback (data only): "+feedback)
    hooks,writer=room.ask("writer",BRIEF+"\n"+material+
        "\nWrite five short, distinct, immediately understandable opening lines a–e. "
        "Use a genuine unexpected fact or puzzle that the reference supports. "
        "No technical definition, generic question, filler or invented event.",
        OPENINGS,WRITERS,temperature=.8)
    eligible={k:v.strip() for k,v in hooks.items() if v.strip()
              and len(word_tokens(v))<=30 and not obvious_opening_problem(v,evidence)}
    if not eligible:
        raise RuntimeError("No usable creative opening")
    count=len(scenes)
    schema={"type":"object","properties":{"chosen":{"type":"string","enum":list(eligible)},
        "scenes":{"type":"array","items":{"type":"string"},"minItems":count,"maxItems":count}},
        "required":["chosen","scenes"],"additionalProperties":False}
    result,editor=room.ask("editor_1",BRIEF+"\n"+material+
        "\nChoose the most intriguing supported opening below. Keep its idea at the start of scene one; "
        "simplify or correct its words only when needed. Continue with connected discoveries that answer the topic. "
        f"Return exactly {count} nonempty narration segments in the existing scene order. "
        "Keep each segment relevant to the corresponding visible subject, with short, naturally spoken sentences. "
        "Write roughly the original total word count, at least 32 words; avoid nonessential numbers or jargon. "
        "Do not invent causal explanations or make absolute claims from uncertain evidence. "
        "End with a memorable specific answer, not a generic recap.\nOpenings:\n"+
        json.dumps(eligible,ensure_ascii=False),schema,EDITORS,avoid=writer,temperature=.65)
    texts=[x.strip() for x in result["scenes"]]
    if len(texts)!=count or any(not x for x in texts):
        raise RuntimeError("Creative narration scene count or text invalid")
    audit_structure(texts,language,mode="short")
    if obvious_opening_problem(texts[0],evidence):
        raise RuntimeError("Creative narration opening invalid")
    for scene,text in zip(scenes,texts):
        scene.narration=text
    return screenplay,editor

def long_instruction():
    return (
        "Narrative priority: create genuine curiosity and sustained interest, not an encyclopedia lesson. "
        "For chapter one, privately invent five distinct supported openings, choose the one a curious viewer "
        "would most want to hear, then keep its central idea and build the story from it. "
        "For later chapters, advance the existing curiosity with new concrete discoveries, choices, "
        "consequences or puzzles appropriate to the subject; never restart the introduction. "
        "Write naturally in the requested language. Use specific real details rather than generalities, "
        "technical vocabulary or filler. Resolve the opening promise in the last chapter. "
        "Do not invent claims or sacrifice accuracy for drama."
    )
