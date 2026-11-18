"""Fast smoke: a NASA Pluto cryovolcano must not stand for Earth's magma."""
import pytest
from media_validation import ValidationError, reject_offtopic_science_source


def test_real_archive_69_source_slug_rejected():
    with pytest.raises(ValidationError, match="Off-topic planetary"):
        reject_offtopic_science_source(
            "Why Do Some Volcanoes Erupt Without Warning?",
            "PlutoInAMinuteEvidenceOfPossibleFrozenVolcanoes "
            "https://archive.org/details/PlutoInAMinuteEvidenceOfPossibleFrozenVolcanoes"
        )


@pytest.mark.parametrize("title,source", [
    ("Why Do Some Volcanoes Erupt Without Warning?", "Icelandic volcano lava"),
    ("Why Do Some Volcanoes Erupt Without Warning?", "NASA Earth volcano"),
    ("What Causes Volcanoes on Pluto?", "NASA Pluto frozen volcanoes"),
    ("Can Mars Have Volcanoes?", "Mars volcano documentary"),
    ("How do hurricanes work?", "NASA Pluto documentary"),
])
def test_no_false_domain_rejection(title, source):
    reject_offtopic_science_source(title, source)


def test_explicit_offplanet_volcanic_clip_rejected():
    with pytest.raises(ValidationError):
        reject_offtopic_science_source(
            "Volcano eruption danger", "NASA video of methane ice volcanoes on Titan")
