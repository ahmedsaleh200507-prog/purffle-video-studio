"""Regression tests for ZIP report.json stage=script malformed JSON."""
from types import SimpleNamespace

import pytest

from long_script import BATCH_SIZES, build_documentary, count_words, validate_batch


def chapter(n):
    return {
        "title": f"Chapter {n}",
        "narration": ("Volcanoes reveal how Earth's underground heat and gases "
                      "combine with rising magma to create different eruptions. " * 9).strip(),
    }


class FakeGroq:
    def __init__(self, *, invalid_once=False, invalid_always=False):
        self.calls = 0
        self.requests = []
        self.invalid_once = invalid_once
        self.invalid_always = invalid_always
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        self.calls += 1
        size = BATCH_SIZES[min((self.calls - 1), len(BATCH_SIZES) - 1)]
        if self.invalid_once and self.calls == 1 or self.invalid_always:
            content = '{"chapters":['
        else:
            content = __import__("json").dumps({
                "chapters": [chapter(n) for n in range(size)]
            })
        return SimpleNamespace(choices=[
            SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))
        ])


def test_batch_accepts_around_100_words():
    example = chapter(1)
    assert 90 <= count_words(example["narration"]) <= 135
    assert validate_batch({"chapters": [example]}, ["One"]) == [example]


def test_generates_four_strict_json_batches_with_14_chapters():
    client = FakeGroq()
    result = build_documentary("Why do volcanoes erupt?", client=client, sleep=lambda _: None)
    assert len(result) == 14
    assert client.calls == 4
    assert all(call["response_format"]["json_schema"]["strict"] for call in client.requests)
    assert all(call["model"] == "openai/gpt-oss-20b" for call in client.requests)


def test_retry_on_truncated_json_then_continue():
    class OneInvalid(FakeGroq):
        def create(self, **kwargs):
            self.requests.append(kwargs)
            self.calls += 1
            if self.calls == 1:
                content = '{"chapters":['
            else:
                success_index = self.calls - 2
                # 4 batches total; failed request does not move batch offset.
                batch_index = 0 if success_index < 1 else min(success_index, 3)
                content = __import__("json").dumps({
                    "chapters": [chapter(n) for n in range(BATCH_SIZES[batch_index])]
                })
            return SimpleNamespace(choices=[
                SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))
            ])

    client = OneInvalid()
    result = build_documentary("Why do volcanoes erupt?", client=client, sleep=lambda _: None)
    assert len(result) == 14
    assert client.calls == 5


def test_never_returns_partial_script_after_three_bad_responses():
    client = FakeGroq(invalid_always=True)
    with pytest.raises(RuntimeError, match="script_batch_1_invalid_after_3_attempts"):
        build_documentary("Why do volcanoes erupt?", client=client, sleep=lambda _: None)
    assert client.calls == 3


def test_wrong_chapter_count_not_accepted():
    with pytest.raises(ValueError, match="script_chapter_count_mismatch"):
        validate_batch({"chapters": [chapter(1)]}, ["A", "B"])


def test_empty_or_short_script_rejected():
    with pytest.raises(ValueError, match="bad_length"):
        validate_batch({"chapters": [{"title": "A", "narration": "Only three words."}]}, ["A"])
