"""Offline V3 regression: new filmable topics, German science, current Pexels API."""
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from media_first import _grounded_candidates
from science_fact_guard import validate_unsourced_quantities
from topic_footage import related_to_topic, words
from video_sources import ProviderRegistry


@pytest.mark.parametrize("title,expected", [
    ("Why Do Bees Dance?", "bee"),
    ("How Do Cats Purr?", "cat"),
    ("What Happens When Trains Brake?", "train"),
    ("Why Do Earthquakes Happen?", "earthquake"),
    ("How Do Rockets Reach Space?", "rocket"),
    ("Wie funktionieren Busse?", "bus"),
    ("Warum tanzen Bienen?", "bee"),
    ("Warum schnurren Katzen?", "cat"),
    ("Wie funktionieren Züge?", "train"),
])
def test_unseen_filmable_topics_have_grounded_queries_without_groq(title, expected):
    shots = _grounded_candidates(title, None)
    assert len(shots) >= 3
    assert all(x["object"] == expected for x in shots)
    assert all(expected in words(x["visual_search_query"]) for x in shots)
    assert all(related_to_topic(title, x["object"], x["visual_search_query"])
               for x in shots)


def test_unknown_abstract_topic_still_does_not_invent_stock():
    assert _grounded_candidates("Obscure xyzqvx abstract invention", None) == []


@pytest.mark.parametrize("title,spoken", [
    ("Warum entstehen Vulkane?", "Die Lava erreicht 1.500 Grad."),
    ("Wie entstehen Inseln?", "Der Berg ist 200 Kilometer breit."),
    ("Was passiert bei einem Hurrikan?", "Der Druck sinkt um 30 Millibar."),
    ("Wieso gibt es Blitze?", "Es sind 300 Millionen Volt."),
    ("Wie lange leben Schildkröten?", "Sie können 150 Jahre leben."),
    ("Why do bees fly?", "They can fly at 20 km/h."),
])
def test_unsourced_german_and_english_numbers_blocked_before_voice(title, spoken):
    script = SimpleNamespace(scenes=[SimpleNamespace(narration=spoken)])
    with pytest.raises(RuntimeError, match="unverified_quantitative_claim"):
        validate_unsourced_quantities(script, title)


def test_plain_german_explainer_without_measurements_is_not_falsely_blocked():
    script = SimpleNamespace(scenes=[SimpleNamespace(
        narration="Vulkane können am Meeresboden entstehen und neues Land bilden.")])
    validate_unsourced_quantities(script, "Wie entstehen Vulkaninseln?")


@dataclass
class Item:
    source: str
    id: str
    kind: str
    url: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0
    query: str = ""
    rank: int = 0
    text: str = ""
    credit: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def key(self):
        return (self.source, self.id)


def test_pexels_search_uses_non_deprecated_v1_video_api_and_both_orientations(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "dummy-test-key")
    client = Mock()
    client.get.return_value = {"videos": [{
        "id": 88, "url": "https://www.pexels.com/video/lava-88/",
        "user": {"name": "Photographer"}, "duration": 12,
        "video_files": [{
            "link": "https://videos.pexels.com/lava.mp4",
            "width": 3840, "height": 2160, "file_type": "video/mp4"
        }]
    }]}
    reg = ProviderRegistry(Item, client=client)
    result = reg.search("pexels", "volcano lava")
    assert len(result) == 1
    assert result[0].extra["license"]["id"] == "PEXELS"
    args, kwargs = client.get.call_args
    assert args[0] == "https://api.pexels.com/v1/videos/search"
    assert kwargs["params"]["query"] == "volcano lava"
    assert "orientation" not in kwargs["params"]
    assert kwargs["headers"] == {"Authorization": "dummy-test-key"}
