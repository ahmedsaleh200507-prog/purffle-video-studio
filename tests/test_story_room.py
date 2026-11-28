from story_room import (StoryRoom, CRITERIA, RED_FLAGS, REJECTED_AURORA,
                        opening_problem, check_verdict)

GOOD = ("Some volcanoes blast rock into the sky. Others erupt less violently. "
        "As magma rises, pressure falls and gas bubbles expand. Runny magma lets gas escape "
        "more easily. Sticky magma can trap gas, allowing pressure to build until an explosive eruption takes place.")

def verdict(text,score=8,flag=False):
    return {"scores":dict.fromkeys(CRITERIA,score),"feedback":"Improve the opening.",
            "red_flags":dict.fromkeys(RED_FLAGS,flag),
            "opening_quote":text.split(".")[0],"weakest_quote":text.split(".")[0],
            "reason_to_continue":"Find the cause of the opening contrast."}

class FakeRoom(StoryRoom):
    def __init__(self,text=GOOD,always_high=False):
        self.trace=[]
        self.calls=[]
        self.text=text
        self.always_high=always_high
    def ask(self,role,prompt,schema,preferred,**kw):
        self.calls.append(role)
        if role.startswith("editor"):
            assert kw["avoid"]=="writer"
            return verdict(self.text,10 if self.always_high else (7 if role=="editor_1" else 8)),"editor"
        return {"angle":"contrast","beats":["start","cause","result"],"narration":self.text},"writer"

def test_good_draft_needs_only_two_calls():
    room=FakeRoom(always_high=True)
    result=room.generate("Why do volcanoes erupt?","en","Reference",word_range=(32,95))
    assert result["editorial_pass"]
    assert room.calls==["writer","editor_1"]

def test_one_rewrite_then_independent_review():
    room=FakeRoom()
    result=room.generate("Why do volcanoes erupt?","en","Reference",word_range=(32,95))
    assert result["editorial_pass"]
    assert room.calls==["writer","editor_1","rewrite","editor_2"]
    assert not result["attempts"][0]["accepted"]
    assert result["attempts"][1]["different_models"]

def test_real_rejected_aurora_cannot_pass_even_with_perfect_scores():
    assert opening_problem(REJECTED_AURORA)
    room=FakeRoom(REJECTED_AURORA,True)
    assert not room.generate("Warum leuchten Polarlichter?","de","Reference")["editorial_pass"]
    assert len(room.calls)==4

def test_editor_red_flag_overrides_score():
    assert not check_verdict(verdict(GOOD,10,True),GOOD)
    v=verdict(GOOD,10)
    v["red_flags"]["unsupported_claims"]=True
    assert not check_verdict(v,GOOD)

def test_editor_must_quote_actual_script():
    v=verdict(GOOD,10)
    v["opening_quote"]="Made up"
    assert not check_verdict(v,GOOD)

def test_same_model_cannot_approve():
    class Same(FakeRoom):
        def ask(self,role,*args,**kw):
            data,model=super().ask(role,*args,**kw)
            return data,"writer"
    assert not Same(always_high=True).generate("Why do volcanoes erupt?","en","Reference",word_range=(32,95))["editorial_pass"]

def test_unavailable_editor_preserves_draft_without_approval():
    class Unavailable(FakeRoom):
        def ask(self,role,*args,**kw):
            if role.startswith("editor"):
                raise RuntimeError("independent_story_model_unavailable")
            return super().ask(role,*args,**kw)
    result=Unavailable().generate("Why do volcanoes erupt?","en","Reference",word_range=(32,95))
    assert not result["editorial_pass"]
    assert result["narration"]==GOOD
    assert "unavailable" in result["attempts"][0]["structural_error"]

def test_shared_contract_adapts_to_subject():
    from editorial_standard import AUDIENCE_BRIEF, long_brief
    for brief in (AUDIENCE_BRIEF,long_brief()):
        assert "volcano" not in brief.lower()
        assert "documented turning point" in brief
        assert "design tradeoff" in brief
        assert "distinctive behavior" in brief
        assert "Do not force a contrast" in brief

def test_topic_and_reference_reach_writer_and_editor():
    class Inspect(FakeRoom):
        def ask(self,role,prompt,schema,preferred,**kw):
            assert self.topic in prompt and self.evidence in prompt
            assert "narrative approach appropriate to it" in prompt
            return super().ask(role,prompt,schema,preferred,**kw)
    for topic,lang,evidence in [
        ("A fictional clock","en","A fictional workshop tests two clock designs."),
        ("Ein fiktiver Hafen","de","Ein fiktiver Hafen erhält eine neue Brücke.")]:
        room=Inspect(always_high=True)
        room.topic,room.evidence=topic,evidence
        room.generate(topic,lang,evidence,word_range=(32,95))
        assert room.calls==["writer","editor_1"]

def test_v5_falsely_approved_openings_are_blocked():
    from story_room import obvious_opening_problem
    en="A diver once saw an octopus’s side pulse twice, then feel a stronger thump as it moved."
    de="Ein einzelnes Elektron schießt entlang des Erdmagnetfelds bis zu den Polen, wo es mit Sauerstoff- und Stickstoffmolekülen kollidiert."
    assert obvious_opening_problem(en,"An octopus has three hearts.")=="unsupported_eyewitness_anecdote"
    assert obvious_opening_problem(de,"Elektronen folgen dem Erdmagnetfeld.")=="technical_mechanism_before_audience_context"
    assert not obvious_opening_problem("An octopus has three hearts.","An octopus has three hearts.")
    assert not obvious_opening_problem("A witness once saw the bridge collapse.","A witness once saw the bridge collapse.")

def test_v5_bad_opening_cannot_pass_with_high_scores():
    room=FakeRoom("A diver once saw an octopus’s side pulse twice. "+GOOD,True)
    result=room.generate("Octopus hearts","en","An octopus has three hearts.",word_range=(32,95))
    assert not result["editorial_pass"]
    assert "unsupported_eyewitness" in result["attempts"][-1]["structural_error"]
