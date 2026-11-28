import pytest
from temporal_vision_pilot import score
def test_correct_moving_and_frozen():
    assert score('{"first":true,"second":false,"third":true}',"moving")["correct"]==3
    assert score('{"first":true,"second":false,"third":false}',"frozen")["correct"]==3
def test_same_answer_cannot_pass_both():
    raw='{"first":true,"second":false,"third":true}'
    assert score(raw,"frozen")["false_positive"]==1
def test_abstention_and_invalid_not_passed():
    assert score('{"first":true,"second":null,"third":false}',"frozen")["correct"]==2
    with pytest.raises(ValueError):
        score('{"first":"yes","second":false,"third":true}',"moving")


def test_short_answer_strict():
    from temporal_vision_pilot import parse_short_answer
    assert parse_short_answer("Yes.") is True
    assert parse_short_answer("NO") is False
    assert parse_short_answer("Uncertain") is None
    with pytest.raises(ValueError):
        parse_short_answer("There are people walking.")
def test_three_independent_questions_and_raw_answer_retention():
    from temporal_vision_pilot import local_verdict
    answers=iter(["Yes","No","unclear prose"])
    row=local_verdict(None,None,"frozen",ask=lambda *_:next(answers))
    assert row["correct"]==2 and row["invalid_answers"]==1
    assert row["answers"][-1]=="unclear prose"
