"""Coverr Nov 2026 free video API: real footage, correct license, no leaked JWT.

No live requests or API keys. The production integration uses the existing
FFprobe, real-motion, local CLIP, per-scene metadata and dedupe checks.
"""
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import Mock
import json
import os

import pytest

from video_sources import ProviderRegistry, JsonClient, LicenseValidator, ProviderError


@dataclass
class Item:
    source: str
    id: str
    kind: str
    url: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0
    credit: str = ""
    query: str = ""
    rank: int = 0
    text: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.source}:{self.id}"


def clip(**overrides):
    data = dict(
        id="mfQX42NS6w",
        title="Ocean waves crashing against cliffs",
        description="Real cinematic sea waves crashing on a rocky coast",
        tags=["ocean", "waves", "cliffs"],
        is_ai_generated=False,
        is_premium=False,
        is_sponsored=False,
        premium=False,
        sponsored=False,
        max_width=3840,
        max_height=2160,
        duration=12.7,
        slug="ocean-waves-crashing-against-cliffs",
        creator={"name": "Filmmaker", "url": "https://coverr.co/filmmaker"},
        urls={"mp4": "https://storage.coverr.co/videos/abcd1234?token=PRIVATE_TEST_JWT",
              "mp4_preview": "https://storage.coverr.co/videos/abcd1234/preview?token=PRIVATE_TEST_JWT"}
    )
    data.update(overrides)
    return data


@pytest.fixture
def reg(monkeypatch):
    monkeypatch.setenv("COVERR_API_KEY", "private-secret-test-key")
    client=Mock()
    client.get.return_value={"hits": [clip()]}
    return ProviderRegistry(Item, client=client)


def test_original_stock_only_returns_full_quality_mp4_with_license_and_credit(reg):
    items=reg.search("coverr-video","ocean waves cliffs")
    assert len(items)==1
    x=items[0]
    assert x.kind=="video" and x.source=="coverr-video"
    assert x.url.endswith("PRIVATE_TEST_JWT") and "/preview" not in x.url
    assert x.width==3840 and x.height==2160 and x.duration==12.7
    assert x.extra["signed_download_url_private"] is True
    assert x.extra["coverr_download_tracking_required"] is True
    lic=x.extra["license"]
    assert lic["id"]=="COVERR" and lic["url"]=="https://coverr.co/license"
    assert lic["attribution_required"] is True
    assert "Filmmaker" in lic["attribution"]
    assert "https://coverr.co/" in lic["attribution"]
    assert LicenseValidator.validate(lic)
    assert reg.client.get.call_args.args==("https://api.coverr.co/videos",)
    assert reg.client.get.call_args.kwargs["headers"]=={"x-api-key":"private-secret-test-key"}
    assert reg.client.get.call_args.kwargs["params"]["filter"]=="is_ai_generated:false"


@pytest.mark.parametrize("bad", [
    {"is_ai_generated":True},
    {"is_ai_generated":None},
    {"is_premium":True},
    {"is_sponsored":True},
    {"sponsored_by":"Shutterstock"},
    {"partner":"iStock"},
    {"premium":True},
    {"watermarked":True},
    {"access_tier":"premium"},
    {"source":"other-service"},
    {"urls":{"mp4":"https://evil.invalid/videos/asset.mp4"}},
    {"urls":{"mp4":"http://storage.coverr.co/videos/asset.mp4"}},
    {"urls":{"mp4":"https://storage.coverr.co/preview/asset.mp4"}},
    {"urls":{"mp4":"https://storage.coverr.co/videos/asset/preview"}},
    {"urls":{"mp4_preview":"https://storage.coverr.co/videos/x/preview"}},
    {"max_width":640,"max_height":360},
])
def test_rejects_ai_premium_sponsored_low_quality_or_unsafe_media(reg,bad):
    reg.client.get.return_value={"hits":[clip(**bad)]}
    assert reg.search("coverr-video","ocean waves cliffs")==[]


def test_report_real_download_via_patch_only_and_obey_free_budget(reg,monkeypatch):
    x=reg.search("coverr-video","ocean waves")[0]
    reg.track_download(x)
    reg.client.patch.assert_called_once_with(
        "https://api.coverr.co/videos/mfQX42NS6w/stats/downloads",
        headers={"x-api-key":"private-secret-test-key"})
    monkeypatch.setenv("PURFFLE_COVERR_MAX_CALLS","2")
    # 1 search + 1 PATCH consumed the quota; refuse future requests.
    assert reg.search("coverr-video","night clouds")==[]
    assert reg.events[-1]["status"]=="quota_budget"
    reg.client.get.assert_called_once()


def test_missing_coverr_key_refuses_network_and_no_fallback(monkeypatch):
    monkeypatch.delenv("COVERR_API_KEY",raising=False)
    c=Mock()
    r=ProviderRegistry(Item,client=c)
    assert not next(x["enabled"] for x in r.health() if x["provider"]=="coverr-video")
    assert r.search("coverr-video","ocean waves")==[]
    c.get.assert_not_called()


def test_signed_video_api_response_is_never_cached(tmp_path):
    response=Mock(status_code=200,headers={})
    response.__enter__=Mock(return_value=response)
    response.__exit__=Mock(return_value=False)
    response.iter_content.return_value=[
        json.dumps({"hits":[clip()]}).encode("utf-8")]
    session=Mock()
    session.get.return_value=response
    client=JsonClient(tmp_path,session=session)
    data=client.get("https://api.coverr.co/videos",
        {"query":"ocean waves"},{"x-api-key":"secret"})
    assert "PRIVATE_TEST_JWT" in json.dumps(data)
    assert not list(tmp_path.glob("*.json"))
    assert "secret" not in repr(list(tmp_path.iterdir()))


def test_tracking_validates_status_and_does_not_log_secret(tmp_path):
    session=Mock()
    response=Mock(status_code=204)
    response.__enter__=Mock(return_value=response)
    response.__exit__=Mock(return_value=False)
    session.patch.return_value=response
    client=JsonClient(tmp_path,session=session)
    assert client.patch("https://api.coverr.co/videos/mfQX42NS6w/stats/downloads",
                        headers={"x-api-key":"private-secret"}) is True
    session.patch.assert_called_once()
    response.status_code=429
    with pytest.raises(ProviderError,match="http_429") as e:
        client.patch("https://api.coverr.co/videos/mfQX42NS6w/stats/downloads",
                     headers={"x-api-key":"private-secret"})
    assert "private-secret" not in str(e.value)


def test_final_source_artifact_never_contains_signed_coverr_url():
    repo=Path(__file__).resolve().parents[1]
    runtime=(repo/"scripts"/"studio_runtime.py").read_text()
    assert 'self.registry.track_download(item)' in runtime
    assert 'item.url = license_info["source_page"]' in runtime
    for name in ("videos.yml","one-german-bathroom-mirror-20261118.yml",
                 "one-video-volcanic-island-20261118.yml",
                 "daily-life-five-20261118.yml"):
        text=(repo/".github"/"workflows"/name).read_text()
        sources = next(line for line in text.splitlines() if "VISUAL_SOURCES:" in line)
        assert "coverr-video" in sources and "freenaturestock-video" in sources
        assert "secrets.COVERR_API_KEY" in text
        assert "PURFFLE_COVERR_MAX_CALLS: '5'" in text
