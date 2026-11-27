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
        if role=="story_architect":
            return {"angles":[dict(hook="A volcano can blast rock.",viewer_question="Why?",
                supported_answer="Trapped gas",fact_chain="Pressure falls; bubbles expand",
                final_insight="Gas pressure drives explosions",why_interesting="Different eruptions")
                for _ in range(3)]},"architect"
        if role=="choose_story":
            return {"winner":0,"feedback":"Explain the contrast."},"planner_editor"
        if role=="compare":
            return {"winner":0,"scores":[dict.fromkeys(CRITERIA,7),dict.fromkeys(CRITERIA,6)],
                    "feedback":"Open with a concrete observation."},"editor"
        if role.startswith("final_editor"):
            score=10 if self.always_high else (7 if role=="final_editor_1_2" else 8)
            return verdict(self.text,score),"judge_"+role[-1]
        return {"angle":"contrast","beats":["start","cause","result"],"narration":self.text},("writer_b" if role=="writer_2" or role.startswith("rewrite") else "writer_a")

def test_rewrite_after_one_editor_rejects():
    result=FakeRoom().generate("Why do volcanoes erupt?","en","Reference",word_range=(32,95))
    assert result["editorial_pass"]
    assert len(result["attempts"])==2
    assert not result["attempts"][0]["accepted"]
    assert result["attempts"][1]["different_models"]

def test_real_rejected_aurora_cannot_pass_even_with_perfect_scores():
    assert opening_problem(REJECTED_AURORA)
    result=FakeRoom(REJECTED_AURORA,True).generate("Warum leuchten Polarlichter?","de","Reference")
    assert not result["editorial_pass"]
    assert len(result["attempts"])==4

def test_editor_red_flag_overrides_score():
    assert not check_verdict(verdict(GOOD,10,True),GOOD)

def test_editor_must_quote_actual_script():
    v=verdict(GOOD,10)
    v["opening_quote"]="Made up"
    assert not check_verdict(v,GOOD)

def test_same_model_cannot_be_both_editors():
    class Same(FakeRoom):
        def ask(self,role,*args,**kw):
            data,model=super().ask(role,*args,**kw)
            return data,("same_judge" if role.startswith("final_editor") else model)
    assert not Same(always_high=True).generate("Why do volcanoes erupt?","en","Reference")["editorial_pass"]

def test_good_original_is_not_needlessly_rewritten():
    room=FakeRoom(always_high=True)
    result=room.generate("Why do volcanoes erupt?","en","Reference",word_range=(32,95))
    assert result["editorial_pass"]
    assert len(result["attempts"])==1
    assert not any(x.startswith("rewrite") for x in room.calls)
    assert room.calls[:2]==["story_architect","choose_story"]

def test_cross_model_rewrite_is_requested_after_both_originals_fail():
    class RejectFirstTwo(FakeRoom):
        def ask(self,role,prompt,schema,preferred,**kw):
            data,model=super().ask(role,prompt,schema,preferred,**kw)
            if role.startswith("final_editor_1_") or role.startswith("final_editor_2_"):
                data["scores"]=dict.fromkeys(CRITERIA,7)
            if role.startswith("rewrite"):
                assert kw["avoid"] in ("writer_a","writer_b")
                model="third_writer"
            return data,model
    result=RejectFirstTwo(always_high=True).generate("Why do volcanoes erupt?","en","Reference",word_range=(32,95))
    assert result["editorial_pass"]
    assert len(result["attempts"])==3
    assert result["attempts"][-1]["writer"]=="third_writer"
