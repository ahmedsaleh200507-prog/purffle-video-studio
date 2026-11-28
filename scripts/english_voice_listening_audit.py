"""Listening candidates only: no production profile change."""
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import local_voice
from piper.config import SynthesisConfig

TEXT = ("A volcano can blast rock high into the sky. The force starts deep underground. "
        "Molten rock is called magma. It can rise because it is less dense than surrounding rock. "
        "Near the surface, pressure drops and gas bubbles expand. Runny magma lets gas escape more easily. "
        "Sticky magma can trap that expanding gas, building pressure that drives an explosive eruption.")

def main():
    root=Path("english-listening")
    root.mkdir(exist_ok=True)
    os.environ["PURFFLE_NATURAL_VOICE"]="1"
    original_loader=local_voice._load_voice
    voice=original_loader("en")
    parameters=inspect.signature(voice.phoneme_ids_to_audio).parameters
    if "syn_config" not in parameters:
        raise RuntimeError("Pinned Piper does not expose expected synthesis config")
    profiles={
        "C":None,
        "D":dict(length_scale=1.07,noise_scale=.55,noise_w_scale=.85),
        "E":dict(length_scale=.96,noise_scale=.72,noise_w_scale=.95),
        "F":dict(length_scale=1.02,noise_scale=.65,noise_w_scale=1.10),
    }
    baseline=None
    for name,profile in profiles.items():
        def synth(ids,**kwargs):
            if profile is not None:
                kwargs["syn_config"]=SynthesisConfig(**profile)
            return voice.phoneme_ids_to_audio(ids,**kwargs)
        try:
            local_voice._load_voice=lambda lang: SimpleNamespace(
                config=voice.config,phonemize=voice.phonemize,phoneme_ids_to_audio=synth)
            speech=local_voice.synthesize(TEXT,root/name,SimpleNamespace(language="en"))
            tokens=[w.text for w in speech.words]
            if baseline is None:
                baseline=tokens
            assert tokens==baseline
            assert speech.provenance["isolated_pronunciation_fallback_sentences"]==0
            assert all(w.start<w.end<=speech.duration for w in speech.words)
            (root/f"{name}.json").write_text(json.dumps({
                "profile":profile,"duration":speech.duration,"provenance":speech.provenance,
                "words":[{"text":w.text,"start":w.start,"end":w.end} for w in speech.words]
            },indent=2))
            print("[LISTENING CANDIDATE]",name,speech.duration,flush=True)
        finally:
            local_voice._load_voice=original_loader
    # Diagnose the known long passage failure without compromising the candidates.
    from purffle_shorts.timing import tokenize
    passage=("A blue whale can be longer than a city bus. It feeds on tiny animals called krill, "
             "even though it is the largest animal alive. It opens its enormous mouth, and the water "
             "flows back out through special plates. The krill stay inside, so one gulp can collect a great "
             "deal of food. When the whale dives, it has to hold its breath. Its body stores oxygen in the "
             "blood and muscles, allowing it to spend time beneath the waves. Then it returns to the surface "
             "to breathe again.")
    diagnostics=[]
    for tokens in local_voice._sentence_groups(tokenize(passage,"en")):
        try:
            local_voice._context_chunks(voice,tokens)
        except ValueError as exc:
            phonemes=local_voice._context_phonemes(voice," ".join(tokens))
            diagnostics.append({"tokens":tokens,"error":str(exc),"context":phonemes,
                                "isolated":[local_voice._context_phonemes(voice,t) for t in tokens]})
    (root/"long-context-diagnostics.json").write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2))
    print("[LONG CONTEXT DIAGNOSTICS]",json.dumps(diagnostics,ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
