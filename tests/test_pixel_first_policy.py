import pytest
from types import SimpleNamespace
from media_validation import ValidationError,SceneMatcher,SceneSpec
from pixel_first_policy import metadata_rank,action_rank,corroborates,confirmed
class Matcher:
    def validate_metadata(self,spec,text):
        raise ValidationError(text)
    def metadata_score(self,spec,text):
        return .12
def test_missing_tags_deferred_but_not_other_errors():
    assert metadata_rank(Matcher(),None,"Scene metadata lacks object/action grounding (score 0.120)")==(.12,"deferred")
    assert metadata_rank(Matcher(),None,"Scene metadata does not describe the requested action")==(.12,"deferred")
    with pytest.raises(ValidationError):
        metadata_rank(Matcher(),None,"Incomplete structured scene")
def test_explicit_contradiction_and_child_never_deferred():
    c={"family":"lava_flow","metadata_keywords":["lava"]}
    assert action_rank(c,"Hawaii nature")=="pixel_review_required"
    assert action_rank(c,"ocean without lava")=="reject"
    assert action_rank(c,"animated volcano")=="reject"
    assert action_rank({"sentence_contracts":[c]},"no lava")=="reject"
def test_independent_verdict_must_be_explicit():
    assert corroborates([[1,0,0],[2,1,0],[0,1,2]])
    assert not corroborates([[1,2,0],[2,1,0],[0,1,2]])
    assert confirmed([True,False,False])
    assert not confirmed([True,None,False])
    assert not confirmed([True,True,False])
def test_default_match_remains_strict():
    import inspect
    assert inspect.signature(SceneMatcher.match).parameters["allow_sparse_metadata"].default is False
