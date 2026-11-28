from visual_selection_proof import specs,match_case,action_case
from media_validation import ValidationError

def test_metadata_does_not_change_for_negative_control():
    seen=[]
    class Matcher:
        def match(self,path,spec,metadata,**kwargs):
            seen.append((spec,metadata))
            if path=="wrong":
                raise ValidationError("wrong pixels")
            return {"visual_score":.3}
    spec=specs()["people"]
    assert match_case(Matcher(),"correct",spec,True)["pass"]
    assert match_case(Matcher(),"wrong",spec,False)["pass"]
    assert seen[0]==seen[1]

def test_false_acceptance_is_a_failure():
    class Matcher:
        def match(self,*a,**kw):
            return {"visual_score":.3}
    row=match_case(Matcher(),"wrong",specs()["whale"],False)
    assert row["accepted"] and not row["pass"]

def test_same_subject_action_requires_matching_pixels():
    frames=[object(),object(),object()]
    assert action_case(frames,False,lambda *_:[[.2,.3]]*3)["pass"]
    assert not action_case(frames,False,lambda *_:[[.35,.2]]*3)["pass"]
