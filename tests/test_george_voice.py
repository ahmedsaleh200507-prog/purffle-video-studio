from types import SimpleNamespace
import pytest
import george_voice as g
import local_voice

def test_user_approved_lock(monkeypatch):
    monkeypatch.setenv("PURFFLE_ENGLISH_NARRATOR","george")
    assert local_voice.provenance("en")==g.provenance()
    assert local_voice.provenance("de")["model"]=="de_DE-thorsten-medium"
    assert g.provenance()["model"]=="bm_george"

def test_model_duration_mapping_keeps_original_punctuation():
    assert g._map_tokens(["A","volcano."],[("A",.1,.2),("volcano",.2,.8),(".",.8,.9)],1.)==[("A",.1,.2),("volcano.",.2,.8)]

@pytest.mark.parametrize("rows",[
    [("A",.1,.2),("mountain",.2,.8)],
    [("A",.1,.3),("volcano",.1,.8)],
    [("A",.1,.2),("volcano",.2,1.2)],
])
def test_unverified_timings_are_refused(rows):
    with pytest.raises(RuntimeError):
        g._map_tokens(["A","volcano."],rows,1.)

def test_missing_asr_proof_and_changed_voice_refused():
    p=g.provenance()
    with pytest.raises(RuntimeError):
        g.verify_provenance(p)
    p["actual_wav_alignment"]={"verified":True,"asr_model":"base.en","words":20,"max_boundary_delta":.3}
    g.verify_provenance(p)
    p["voice_sha256"]="wrong"
    with pytest.raises(RuntimeError):
        g.verify_provenance(p)

def test_no_english_voice_fallback(monkeypatch,tmp_path):
    monkeypatch.setenv("PURFFLE_ENGLISH_NARRATOR","george")
    def fail(*args,**kwargs):
        raise RuntimeError("George unavailable")
    monkeypatch.setattr(g,"synthesize",fail)
    with pytest.raises(RuntimeError,match="George unavailable"):
        local_voice.synthesize("A volcano erupts.",tmp_path,SimpleNamespace(language="en"))
