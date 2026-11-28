from visual_ensemble_proof import decision,rank,CASES
def test_wrong_subject_rejected_if_secondary_disagrees():
    a=[[3,2,1]]*3
    b=[[2,3,1]]*3
    assert not decision(a,b,0,True)["accepted"]
def test_required_motion_cannot_be_rescued_by_similarity():
    a=[[3,2,1]]*3
    assert decision(a,a,0,False)["accepted"]
    assert not decision(a,a,0,False,True)["accepted"]
def test_majority_rank_and_five_categories():
    assert rank([[3,2,1],[3,2,1],[1,2,3]],0)
    assert len(CASES)==5
