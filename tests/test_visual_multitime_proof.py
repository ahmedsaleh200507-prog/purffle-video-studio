import pytest
from visual_multitime_proof import windows,stats,evaluate_window,select_window,GROUPS

def test_window_positions_and_limits():
    w=windows(50)
    assert w[0][0]<w[1][0]<w[2][0]
    assert all(a>=0 and a+b<=50 for a,b in w)
    with pytest.raises(ValueError):
        windows(1)

def test_weak_agreement_requires_review():
    a=[[.2,.19,.1]]*3
    b=[[-6,-7,-8]]*3
    row=evaluate_window(a,b,True,lambda:[False,True,False])
    assert not row["candidates"][0]["strong_agreement"]
    assert not any(x["accepted"] for x in row["candidates"])

def test_strong_agreement_can_be_vetoed():
    a=[[.3,.1,.1]]*3
    b=[[2,-6,-8]]*3
    row=evaluate_window(a,b,True,lambda:[False,True,False])
    assert row["candidates"][0]["strong_agreement"]
    assert not row["candidates"][0]["accepted"]

def test_positive_requires_explicit_exclusion_and_motion_when_needed():
    a=[[.3,.1,.1]]*3
    b=[[2,-6,-8]]*3
    row=evaluate_window(a,b,False,lambda:[True,False,False])
    assert select_window([row],0) is row
    assert select_window([row],0,True) is None
    row=evaluate_window(a,b,True,lambda:[True,None,False])
    assert select_window([row],0) is None

def test_no_label_leak_or_missing_review_acceptance():
    a=[[.1,.3,.1]]*3
    b=[[-8,2,-8]]*3
    row=evaluate_window(a,b,True,lambda:[False,True,False])
    assert row["candidates"][1]["accepted"]
    def fail():
        raise RuntimeError("unavailable")
    row=evaluate_window(a,b,True,fail)
    assert row["review_error"]=="RuntimeError"
    assert not any(r["accepted"] for r in row["candidates"])

def test_fresh_sources_distinct():
    assert len(GROUPS["regression"])==len(GROUPS["fresh"])==10
    assert not ({c[2] for c in GROUPS["regression"]}&{c[2] for c in GROUPS["fresh"]})
