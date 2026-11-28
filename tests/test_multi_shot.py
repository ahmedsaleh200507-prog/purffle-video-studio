import pytest
from multi_shot import frame_plan,validate_plan

def shot(n,start=0):
    h=str(n)*64
    return {"id":str(n),"sha256":h,"start":start,
        "license":{"id":"CC0-1.0","url":"https://creativecommons.org/publicdomain/zero/1.0/","source_page":"https://example.com/source"},
        "approval":{"verified":True,"start":start,"seconds":3.,"sha256":h}}

def test_nine_seconds_exact():
    assert frame_plan(9)==[90,90,90]

def test_five_seconds_two_shots():
    assert frame_plan(5)==[75,75]

@pytest.mark.parametrize("duration",[0,3,float("nan"),16])
def test_bad_duration(duration):
    with pytest.raises(ValueError):
        frame_plan(duration)

def test_valid_plan():
    validate_plan([shot(1),shot(2),shot(3)],[90,90,90],30)

def test_duplicate_source():
    with pytest.raises(ValueError,match="duplicate"):
        validate_plan([shot(1),shot(1)],[90,90],30)

def test_wrong_interval():
    with pytest.raises(ValueError,match="different interval"):
        validate_plan([shot(1),shot(2)],[90,91],30)

def test_invalid_license():
    row=shot(1);row["license"]={}
    with pytest.raises(ValueError,match="provenance"):
        validate_plan([row,shot(2)],[90,90],30)

def test_unapproved():
    row=shot(1);row["approval"]["verified"]=False
    with pytest.raises(ValueError,match="not independently approved"):
        validate_plan([row,shot(2)],[90,90],30)

def test_approval_hash_mismatch():
    row=shot(1);row["approval"]["sha256"]="f"*64
    with pytest.raises(ValueError,match="different source"):
        validate_plan([row,shot(2)],[90,90],30)
