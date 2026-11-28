from visual_tiebreak_proof import resolve,adjudicate,HOLDOUT
from visual_ensemble_proof import CASES

def base(a=True,b=False,motion=True,required=False):
    return {"clip":a,"siglip":b,"motion":motion,"require_motion":required,"accepted":a and b and (motion or not required)}

def test_symmetric_rescue():
    for b in (base(),base(False,True)):
        assert resolve(b,0,[True,False,False])["accepted"]
        assert resolve(b,1,[False,True,False])["accepted"]

def test_no_rescue_on_missing_conflicting_or_unknown_evidence():
    for verdict in (None,[True,True,False],[True,None,False],[False,False,False]):
        assert not resolve(base(),0,verdict)["accepted"]

def test_motion_veto_and_agreement_preserved():
    assert not resolve(base(True,False,False,True),0,[True,False,False])["accepted"]
    assert not resolve(base(False,False),0,[True,False,False])["accepted"]
    assert resolve(base(True,True),0)["accepted"]

def test_one_call_and_no_expected_label_leak():
    calls=[]
    def ask():
        calls.append(1)
        return [False,True,False]
    rows=adjudicate([("positive",0,True,base()),("negative",1,False,base(False,True))],ask)
    assert len(calls)==1
    assert rows["negative"]["accepted"] and not rows["negative"]["pass"]

def test_distinct_sources():
    assert len(HOLDOUT)==5
    assert not ({c[2] for c in CASES}&{c[2] for c in HOLDOUT})
