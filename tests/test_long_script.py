"""Regression tests for ZIP report.json stage=script malformed JSON."""
from types import SimpleNamespace

import pytest

from long_script import BATCH_SIZES, build_documentary, count_words, validate_batch


def chapter(n):
    return {
        "title": f"Chapter {n}",
        "narration": ("Volcanoes reveal how Earth's underground heat and gases "
                      "combine with rising magma to create different eruptions. " * 7).strip(),
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
    # The adaptive verifier splits 4 -> 2 -> 1; every attempted response
    # remains invalid, so no partial script may escape.
    assert client.calls == 9


def test_wrong_chapter_count_not_accepted():
    with pytest.raises(ValueError, match="script_chapter_count_mismatch"):
        validate_batch({"chapters": [chapter(1)]}, ["A", "B"])


def test_empty_or_short_script_rejected():
    with pytest.raises(ValueError, match="bad_length"):
        validate_batch({"chapters": [{"title": "A", "narration": "Only three words."}]}, ["A"])

def test_fire_and_ice_trend_uses_new_14_science_chapters_without_changing_volcano():
    from long_script import FIRE_AND_ICE_TOPICS, TOPICS, is_fire_and_ice
    topic = "Ice Age vs Lava: What Happens When a Volcano Erupts Beneath a Glacier?"
    assert is_fire_and_ice(topic)
    assert not is_fire_and_ice("Why do volcanoes erupt?")
    assert len(FIRE_AND_ICE_TOPICS) == len(TOPICS) == 14
    assert FIRE_AND_ICE_TOPICS[0].startswith("A hot volcano")
    client = FakeGroq()
    result = build_documentary(topic, client=client, sleep=lambda _: None)
    assert len(result) == 14
    prompts = [call["messages"][-1]["content"] for call in client.requests]
    assert "glacier" in prompts[0].lower()
    assert "Glaciers" not in prompts[0] or len(prompts[0]) > 0
    assert "steam" in prompts[1].lower()
    assert "subscribe" not in result[0]["narration"].lower()


def test_fire_and_ice_11th_chapter_jargon_is_spoken_plainly():
    from long_script import accessible_science_narration, count_words
    text = (
        "When glaciers retreat, they leave behind cirques—amphitheater‑shaped "
        "hollows—and sharp arêtes that expose the volcanic core."
    )
    result = accessible_science_narration(text)
    assert "cirque" not in result.lower()
    assert "arête" not in result.lower()
    assert "arete" not in result.lower()
    assert "bowl shaped valleys" in result
    assert "steep mountain ridges" in result
    assert not any(ch in result for ch in ("—", "‑", "ê"))
    assert count_words(result) >= count_words(text)


def test_fire_and_ice_narration_avoids_difficult_specialized_words():
    from long_script import accessible_science_narration
    phrase = "A jökulhlaup can become a lahar, while rhyolitic lava hardens."
    spoken = accessible_science_narration(phrase)
    assert "sudden glacier floods" in spoken
    assert "volcanic mudflows" in spoken
    assert "silica rich" in spoken
    assert "jokulhlaup" not in spoken.lower()
    assert "lava hardens" in spoken


class SimulatedGroqJSONRejected(Exception):
    status_code = 400
    body = {"error": {"code": "json_validate_failed"}}


def test_recover_one_transient_groq_json_400_without_splitting():
    from long_script import is_groq_json_validation_error
    assert is_groq_json_validation_error(SimulatedGroqJSONRejected("invalid JSON"))
    class Client:
        def __init__(self):
            self.calls = 0
            self.requests = []
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self.create))
        def create(self, **kwargs):
            self.calls += 1
            self.requests.append(kwargs)
            if self.calls == 1:
                raise SimulatedGroqJSONRejected("json_validate_failed")
            length = [4,4,4,2][self.calls-2]
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=__import__("json").dumps({
                    "chapters":[chapter(n) for n in range(length)]
                })))])
    client=Client()
    result=build_documentary("Why do volcanoes erupt?",client=client,
                             sleep=lambda _:None)
    assert len(result)==14
    assert client.calls==5
    assert all(c["response_format"]["type"]=="json_schema"
               for c in client.requests)


def test_recover_permanently_broken_four_chapter_json_by_verified_2_plus_2():
    """One bad Groq group must not discard valid other chapters or entire film."""
    import re
    class Client:
        def __init__(self):
            self.sizes=[]
            self.chat=SimpleNamespace(
                completions=SimpleNamespace(create=self.create))
        def create(self,**kwargs):
            prompt=kwargs["messages"][-1]["content"]
            match=re.search(r"Write section (\d+) through (\d+)",prompt)
            assert match is not None
            start,end=map(int,match.groups())
            size=end-start+1
            self.sizes.append(size)
            if size==4 and start==1:
                raise SimulatedGroqJSONRejected("json_validate_failed")
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=__import__("json").dumps({
                    "chapters":[chapter(n) for n in range(start,end+1)]
                })))])
    client=Client()
    result=build_documentary(
        "Ice Age vs Lava: What Happens When a Volcano Erupts Beneath a Glacier?",
        client=client,sleep=lambda _:None)
    assert len(result)==14
    assert [x["title"] for x in result] == [
        f"Chapter {n}" for n in range(1,15)]
    assert client.sizes == [4,4,4,2,2,4,4,2]


def test_unrecoverable_groq_401_is_never_retried():
    class Unauthorized(Exception):
        status_code = 401
        body = {"error": {"code": "invalid_api_key"}}
    class Client:
        def __init__(self):
            self.calls=0
            self.chat=SimpleNamespace(
                completions=SimpleNamespace(create=self.create))
        def create(self, **kwargs):
            self.calls+=1
            raise Unauthorized("Authentication failed")
    c=Client()
    with pytest.raises(Unauthorized,match="Authentication failed"):
        build_documentary("Why do volcanoes erupt?",client=c,
                          sleep=lambda _:None)
    assert c.calls==1


def test_single_chapter_json_fallback_has_local_strict_validation():
    """Even in JSON object mode a fabricated, shortened paragraph is rejected."""
    class Client:
        def __init__(self):
            self.calls=[]
            self.chat=SimpleNamespace(
                completions=SimpleNamespace(create=self.create))
        def create(self,**kwargs):
            import re
            prompt=kwargs["messages"][-1]["content"]
            start,end=map(int,re.search(
                r"Write section (\d+) through (\d+)",prompt).groups())
            size=end-start+1
            mode=kwargs["response_format"]["type"]
            self.calls.append((size,mode))
            if size>1 or mode!="json_object":
                raise SimulatedGroqJSONRejected("json_validate_failed")
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=__import__("json").dumps({
                    "chapters":[{"title":"One", "narration":"Too short."}]
                })))])
    c=Client()
    with pytest.raises(RuntimeError,match="script_batch_1_invalid_after_3_attempts"):
        build_documentary("Why do volcanoes erupt?",client=c,
                          sleep=lambda _:None)
    assert (1,"json_object") in c.calls
