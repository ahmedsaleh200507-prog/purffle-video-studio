"""Safe, compact ten-field workflow dispatch tests."""
import pytest
from long_batch_slot import parse_long_slot, choose_slot, main


def test_independent_english_and_german_slots():
    en=choose_slot("en|Why do octopuses have three hearts?",1)
    de=choose_slot("de|Warum haben Oktopusse drei Herzen?",10)
    assert en=={"slot":1,"render":True,"language":"en",
                "topic":"Why do octopuses have three hearts?"}
    assert de["language"]=="de" and de["slot"]==10
    assert choose_slot("",3)=={"slot":3,"render":False}
    assert choose_slot("   ",2)=={"slot":2,"render":False}


@pytest.mark.parametrize("raw",[
    "Why is the sky blue?", "tr|Ne oldu?", "en|", "de|",
    "de|Ein Thema\nen|Another topic", "de|A topic|en|Second",
    "en|A", "fr|Le monde", "de|Another topic\rInjected",
])
def test_invalid_batch_fields_fail_before_model_setup(raw):
    with pytest.raises(ValueError):
        parse_long_slot(raw)


@pytest.mark.parametrize("slot",[0,11,-2])
def test_slot_bounds(slot):
    with pytest.raises(ValueError):
        choose_slot("en|Why do volcanoes erupt?",slot)


def test_output_file_contains_only_selected_video_and_language(tmp_path,monkeypatch):
    p=tmp_path/"github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT",str(p))
    monkeypatch.setenv("LONG_SLOT_TOPIC",
                       "de|Warum haben Oktopusse drei Herzen?")
    assert main(["--slot","7"])==0
    result=p.read_text()
    assert "render=true" in result
    assert "language=de" in result
    assert "topic=Warum haben Oktopusse drei Herzen?" in result
    assert "topic=10" not in result


def test_blank_slot_does_not_set_topic_or_install_tools(tmp_path,monkeypatch):
    p=tmp_path/"github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT",str(p))
    monkeypatch.setenv("LONG_SLOT_TOPIC","")
    assert main(["--slot","6"])==0
    assert p.read_text()=="render=false\n"
