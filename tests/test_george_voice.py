from types import SimpleNamespace
import pytest
import george_voice as g
import local_voice

def test_user_approved_lock(monkeypatch):
    monkeypatch.setenv("PURFFLE_ENGLISH_NARRATOR","joe")
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


def test_pcm_decoder_uses_actual_audio_without_pyav(tmp_path):
    import numpy as np
    import wave
    path=tmp_path/"actual.wav"
    samples=(np.sin(np.arange(24000)*2*np.pi*440/24000)*16000).astype("<i2")
    with wave.open(str(path),"wb") as w:
        w.setparams((1,2,24000,0,"NONE","not compressed"))
        w.writeframes(samples.tobytes())
    audio=g._read_pcm_for_asr(path)
    assert audio.dtype==np.float32 and audio.shape==(16000,)
    assert .47<float(np.max(np.abs(audio)))<.51

def test_asr_receives_pcm_and_rejects_changed_words(monkeypatch,tmp_path):
    import numpy as np
    monkeypatch.setattr(g,"_read_pcm_for_asr",lambda path:np.zeros(16000,dtype=np.float32))
    class Model:
        def transcribe(self,audio,**kwargs):
            assert isinstance(audio,np.ndarray) and audio.shape==(16000,)
            assert "initial_prompt" not in kwargs
            return [SimpleNamespace(words=[SimpleNamespace(word="A",start=.1,end=.2,probability=.99),SimpleNamespace(word="volcano",start=.2,end=.8,probability=.99)])],None
    monkeypatch.setattr(g,"_asr",lambda model:Model())
    rows=[("A",.1,.2),("volcano.",.2,.8)]
    assert g._verify_wav("A volcano.",tmp_path/"actual.wav",["A","volcano."],rows,1.)==("base.en",0.)
    with pytest.raises(RuntimeError,match="actual-audio verification failed"):
        g._verify_wav("A mountain.",tmp_path/"actual.wav",["A","mountain."],rows,1.)
