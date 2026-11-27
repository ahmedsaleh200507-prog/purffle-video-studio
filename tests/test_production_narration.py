"""Offline integration checks: actual production adapter, no paid or live API."""
from types import SimpleNamespace
from production_narration import rewrite_short, polish_long_opening, review_reference
from science_sources import Evidence

class Room:
    def __init__(self, output):
        self.output=output
        self.calls=[]
    def ask(self, role, prompt, schema, preferred, **kwargs):
        self.calls.append((role,kwargs))
        if role=="writer":
            return dict.fromkeys("abcde","A clock can run without electricity."),"writer"
        assert kwargs["avoid"]=="writer"
        return self.output,"editor"

def test_short_changes_only_narration():
    scenes=[SimpleNamespace(narration="A mechanical clock uses a spring.",object="clock",visual_search_query="clock mechanism"),
            SimpleNamespace(narration="The spring drives gears.",object="gears",visual_search_query="clock gears")]
    script=SimpleNamespace(scenes=scenes)
    texts=["A clock can run without electricity. Its spring stores energy when you wind it.",
           "As the spring unwinds, it turns a set of gears that control the movement of the hands."]
    room=Room({"chosen":"a","scenes":texts})
    evidence=Evidence("Mechanical clocks",({"id":"1","title":"Reference","excerpt":"A clock can run without electricity. A wound spring stores energy and turns gears."},),"model_screened_reference")
    result,model=rewrite_short(script,"Mechanical clocks","en",evidence,room=room)
    assert result is script and model=="editor"
    assert [x.narration for x in result.scenes]==texts
    assert [x.visual_search_query for x in result.scenes]==["clock mechanism","clock gears"]
    assert len(room.calls)==2

def test_long_changes_first_chapter_only():
    text="A clock can run without electricity. Its spring stores energy when you wind it."
    chapters=[{"title":"The spring","narration":text,"visual_subject":"clock"},
              {"title":"The gears","narration":"The spring turns gears."}]
    room=Room({"chosen":"a","narration":text})
    result=polish_long_opening("Mechanical clocks","en",chapters,chapters,room=room,word_range=(10,30))
    assert result[0]["visual_subject"]=="clock" and result[1]==chapters[1]
    assert len(room.calls)==2

def test_curated_rewrites_do_not_use_exact_dossier_approval():
    bundle=Evidence("Why do octopuses have three hearts?",({"id":"official-1","title":"octopus","url":"https://ocean.si.edu/ocean-life/invertebrates/octopuses-squids-and-relatives","tier":"editor_reviewed_official_dossier"},),"curated_editor_reviewed")
    result=review_reference(bundle,bundle.topic,"en")
    assert result.method=="creative_dossier_reference"
    assert result.sources[0]["excerpt"]
