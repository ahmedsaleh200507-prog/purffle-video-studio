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
