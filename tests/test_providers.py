"""Offline API contract and license regressions; no keys or external calls."""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import Mock

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from video_sources import JsonClient, LicenseValidator, ProviderError, ProviderRegistry


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


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    for name in ("PIXABAY_API_KEY", "PEXELS_API_KEY", "EUROPEANA_API_KEY", "COVERR_API_KEY", "COVER2", "NPS_API_KEY", "VECTEEZY_API_KEY", "PURFFLE_NO_ATTRIBUTION"):
        monkeypatch.delenv(name, raising=False)


def registry(data=None):
    client = Mock()
    client.get.return_value = data or {}
    return ProviderRegistry(Item, client=client)


@pytest.mark.parametrize("url,lid,allowed", [
    ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0", True),
    ("https://creativecommons.org/publicdomain/mark/1.0/", "PDM-1.0", True),
    ("https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0", True),
    ("https://creativecommons.org/licenses/by-sa/4.0/", "CC-BY-SA-4.0", False),
    ("https://creativecommons.org/licenses/by-nc/4.0/", "CC-BY-NC-4.0", False),
    ("https://creativecommons.org/licenses/by-nd/4.0/", "CC-BY-ND-4.0", False),
    ("https://evil.invalid/?license=creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0", False),
    ("https://creativecommons.org.evil.invalid/licenses/by/4.0/", "CC-BY-4.0", False),
])
def test_license_allowlist(url, lid, allowed):
    info = {"id": lid, "url": url, "creator": "Creator", "source_page": "https://example.org/asset"}
    assert LicenseValidator.validate(info) is allowed


def test_attribution_required_for_by():
    info = {"id": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/",
            "creator": "", "source_page": "https://example.org/asset"}
    assert not LicenseValidator.validate(info)
    info["creator"] = "Person"
    assert LicenseValidator.validate(info)
    info["source_page"] = ""
    assert not LicenseValidator.validate(info)


@pytest.mark.parametrize("source", ["pixabay", "pexels", "europeana-video", "coverr-video"])
def test_missing_keys_do_not_call_api(source):
    reg = registry()
    assert reg.search(source, "street") == []
    reg.client.get.assert_not_called()
    assert reg.events[-1]["status"] == "skipped"


def test_coverr_is_enabled_if_key_present_but_never_assumed_to_have_stock(monkeypatch):
    monkeypatch.setenv("COVERR_API_KEY", "test-secret-do-not-store")
    reg = registry({"hits": []})
    assert reg.search("coverr-video", "street") == []
    reg.client.get.assert_called_once()
    assert reg.client.get.call_args.kwargs["headers"] == {"x-api-key": "test-secret-do-not-store"}
    assert reg.client.get.call_args.kwargs["params"]["filter"] == "is_ai_generated:false"
    assert reg.events[-1]["status"] == "empty"


@pytest.mark.parametrize("source", ["wikimedia-video", "nasa-video", "archive-video"])
def test_empty_results(source):
    reg = registry()
    assert reg.search(source, "no match") == []
    assert reg.events[-1]["status"] == "empty"


@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_http_errors_not_reported_as_empty(status):
    reg = registry()
    reg.client.get.side_effect = ProviderError(f"http_{status}", "request rejected")
    assert reg.search("wikimedia-video", "street") == []
    assert reg.events[-1]["status"] == f"http_{status}"
    reg.search("wikimedia-video", "street again")
    assert reg.client.get.call_count == (1 if status in (403, 429) else 2)


def test_pixabay_selects_real_4k_instead_of_medium(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "test-secret")
    reg = registry({"hits": [{"id": 5, "user": "camera", "pageURL": "https://pixabay.com/videos/id-5/",
        "tags": "man banknote street", "duration": 7,
        "videos": {"medium": {"url": "https://cdn.example.org/720.mp4", "width": 1280, "height": 720},
                   "large": {"url": "https://cdn.example.org/4k.mp4", "width": 3840, "height": 2160}}}]})
    items = reg.search("pixabay", "man banknote")
    assert items[0].url.endswith("4k.mp4")
    assert (items[0].width, items[0].height) == (3840, 2160)
    assert items[0].extra["license"]["id"] == "PIXABAY"
    assert reg.client.get.call_args.kwargs["params"]["video_type"] == "film"


def test_footage_search_inspects_more_candidates_per_single_api_call(monkeypatch):
    """#86: do not stop at Pexels 15 / Pixabay 20 first often-offtopic hits."""
    monkeypatch.setenv("PIXABAY_API_KEY", "test-secret")
    monkeypatch.setenv("PEXELS_API_KEY", "test-secret")
    reg = registry({"hits": []})
    assert reg.search("pixabay", "volcano eruption") == []
    args = reg.client.get.call_args.kwargs
    assert args["params"]["per_page"] == 60
    assert reg.client.get.call_count == 1

    reg.client.get.reset_mock()
    reg.client.get.return_value = {"videos": []}
    assert reg.search("pexels", "volcano eruption") == []
    args = reg.client.get.call_args.kwargs
    assert args["params"]["per_page"] == 50
    assert reg.client.get.call_count == 1
    assert args["params"]["size"] == "large"


def test_nasa_selects_orig_leaves_resolution_unknown():
    reg = registry()
    reg.client.get.side_effect = [
        {"collection": {"items": [{"data": [{"nasa_id": "test", "media_type": "video", "title": "Earth orbit", "center": "GSFC"}]}]}},
        {"collection": {"items": [{"href": "https://images-assets.nasa.gov/video/test/test~small.mp4"},
                                    {"href": "http://images-assets.nasa.gov/video/test/test~orig.mp4"},
                                    {"href": "https://images-assets.nasa.gov/video/test/test~mobile.mp4"}]}}]
    items = reg.search("nasa-video", "earth orbit")
    assert len(items) == 1
    assert items[0].url == "https://images-assets.nasa.gov/video/test/test~orig.mp4"
    assert items[0].width == items[0].height == 0


@pytest.mark.parametrize("field,value", [("description", "Footage courtesy ESA"), ("photographer", "Getty"),
    ("secondary_creator", "European Space Agency"), ("copyright", "NASA Copyright")])
def test_nasa_rejects_third_party_credits(field, value):
    reg = registry({"collection": {"items": [{"data": [{"nasa_id": "test", "media_type": "video", field: value}]}]}})
    assert reg.search("nasa-video", "earth") == []
    assert reg.client.get.call_count == 1


def test_wikimedia_video_type_and_license():
    pages = {}
    for i, (mime, license_url) in enumerate([
        ("video/webm", "https://creativecommons.org/licenses/by/4.0/"),
        ("image/jpeg", "https://creativecommons.org/publicdomain/zero/1.0/"),
        ("video/mp4", "https://creativecommons.org/licenses/by-sa/4.0/"),
        ("video/ogg", "https://creativecommons.org/publicdomain/zero/1.0/"),
    ]):
        pages[str(i)] = {"pageid": i, "title": "File:Street", "imageinfo": [{"mime": mime,
            "url": f"https://upload.wikimedia.org/{i}.webm", "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{i}",
            "width": 1920, "height": 1080, "extmetadata": {"LicenseUrl": {"value": license_url}, "Artist": {"value": "<a>Filmmaker</a>"}}}]}
    reg = registry({"query": {"pages": pages}})
    assert [x.id for x in reg.search("wikimedia-video", "street")] == ["0", "3"]


def test_europeana_string_hasview_and_ambiguous_rights(monkeypatch):
    monkeypatch.setenv("EUROPEANA_API_KEY", "secret")
    good = {"id": "/1/2", "type": "VIDEO", "rights": ["https://creativecommons.org/publicdomain/zero/1.0/"],
            "edmHasView": "https://example.org/movie.webm", "title": ["Street"], "guid": "https://www.europeana.eu/item/1/2"}
    bad = {**good, "id": "bad", "rights": good["rights"] + ["http://rightsstatements.org/vocab/InC/1.0/"]}
    reg = registry({"success": True, "items": [good, bad]})
    items = reg.search("europeana-video", "street")
    assert len(items) == 1
    assert items[0].url == good["edmHasView"]
    assert reg.client.get.call_args.kwargs["headers"] == {"X-Api-Key": "secret"}


def test_archive_rechecks_metadata_license_and_picks_largest():
    reg = registry()
    reg.client.get.side_effect = [
        {"response": {"docs": [{"identifier": "valid"}, {"identifier": "copyrighted"}]}},
        {"metadata": {"licenseurl": "http://creativecommons.org/publicdomain/zero/1.0/", "title": "Ocean"},
         "files": [{"name": "ocean_720.mp4", "width": "1280", "height": "720", "size": "100"},
                   {"name": "ocean.webm", "width": "3840", "height": "2160", "size": "200"}]},
        {"metadata": {"licenseurl": "https://example.org/reserved"}, "files": [{"name": "bad.mp4"}]}]
    items = reg.search("archive-video", "ocean")
    assert len(items) == 1 and items[0].url.endswith("ocean.webm")
    assert items[0].height == 2160
    assert "licenseurl:\"https://creativecommons.org/publicdomain/zero/1.0/\"" in reg.client.get.call_args_list[0].kwargs["params"]["q"]


def response(data, status=200):
    r = Mock(status_code=status, headers={})
    r.__enter__ = Mock(return_value=r)
    r.__exit__ = Mock(return_value=False)
    r.iter_content.return_value = [json.dumps(data).encode()]
    return r


def test_json_cache_hides_credentials_and_reuses_response(tmp_path):
    session = Mock()
    session.get.return_value = response({"hits": []})
    client = JsonClient(tmp_path, session=session)
    client._last_request.clear()
    assert client.get("https://example.org/api", {"key": "do-not-store-this"}) == {"hits": []}
    assert client.get("https://example.org/api", {"key": "do-not-store-this"}) == {"hits": []}
    assert session.get.call_count == 1
    assert "do-not-store-this" not in " ".join(p.name + p.read_text() for p in tmp_path.iterdir())


def test_error_object_in_http_200_is_not_success(tmp_path):
    session = Mock()
    session.get.return_value = response({"error": "backend unavailable"})
    client = JsonClient(tmp_path, session=session)
    client._last_request.clear()
    with pytest.raises(ProviderError, match="api_error"):
        client.get("https://example.org/api")
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_transport_returns_sanitized_http_status(tmp_path, status):
    session = Mock()
    session.get.return_value = response({}, status)
    client = JsonClient(tmp_path, session=session)
    client._last_request.clear()
    with pytest.raises(ProviderError, match=f"http_{status}") as e:
        client.get("https://example.org/api", {"key": "secret"})
    assert "secret" not in str(e.value)


@pytest.mark.parametrize("text", ["Computer-generated ocean", "Animated octopus", "CGI Earth",
                                      "Ocean simulation", "Earth visualization", "AI-generated banknote"])
def test_explicit_synthetic_footage_rejected(text):
    reg = registry()
    item = Item("wikimedia-video", "x", "video", "https://example.org/x.mp4", text=text)
    item.extra["license"] = {"id": "CC0-1.0", "url": "https://creativecommons.org/publicdomain/zero/1.0/",
                             "source_page": "https://example.org/x"}
    reg._wikimedia = lambda query: [item]
    assert reg.search("wikimedia-video", "ocean") == []


def test_attribution_is_complete_string():
    info = ProviderRegistry.license("CC-BY-4.0", "https://creativecommons.org/licenses/by/4.0/", "Camera Author", "https://example.org/x")
    assert info["attribution_required"] is True
    assert isinstance(info["attribution"], str)
    assert all(value in info["attribution"] for value in ("Camera Author", "CC-BY-4.0", "https://example.org/x", "cropped"))



def test_quota_cooldown_persists_between_clients(tmp_path):
    first_session = Mock()
    first_session.get.return_value = response({}, 429)
    first_session.get.return_value.headers = {"Retry-After": "120"}
    client = JsonClient(tmp_path, session=first_session)
    client._last_request.clear()
    with pytest.raises(ProviderError, match="http_429"):
        client.get("https://example.org/api")
    second_session = Mock()
    second = JsonClient(tmp_path, session=second_session)
    with pytest.raises(ProviderError, match="cooldown"):
        second.get("https://example.org/api", {"q": "different query"})
    second_session.get.assert_not_called()


def test_remaining_zero_still_serves_cached_search(tmp_path):
    session = Mock()
    session.get.return_value = response({"hits": []})
    session.get.return_value.headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "120"}
    client = JsonClient(tmp_path, session=session)
    client._last_request.clear()
    assert client.get("https://example.org/api", {"q": "cached"}) == {"hits": []}
    assert client.get("https://example.org/api", {"q": "cached"}) == {"hits": []}
    with pytest.raises(ProviderError, match="http_429"):
        client.get("https://example.org/api", {"q": "uncached"})
    assert session.get.call_count == 1


# NPS/Vecteezy/COVER2 contracts. No account keys are ever printed.
NPS_ID = "CA91ADBF-BCE3-4434-B3D6-7691D7347758"


def nps_record(**updates):
    row = {
        "id": NPS_ID,
        "permalinkUrl": f"https://www.nps.gov/media/video/view.htm?id={NPS_ID}",
        "title": "Waves on a rocky shore",
        "description": "Moving ocean waves hit a rocky coast",
        "credit": "NPS/Staff",
        "isBRoll": True,
        "isVideoOnly": False,
        "durationMs": 9000,
        "versions": [
            {"url": "https://www.nps.gov/nps-audiovideo/audiovideo/low.mp4",
             "fileType": "video/mp4", "widthPixels": 640, "heightPixels": 360},
            {"url": "https://www.nps.gov/nps-audiovideo/audiovideo/hd.mp4",
             "fileType": "video/mp4", "widthPixels": 1920, "heightPixels": 1080},
            {"url": "https://www.nps.gov/nps-audiovideo/audiovideo/4k.mp4",
             "fileType": "video/mp4", "widthPixels": 3840, "heightPixels": 2160},
        ],
    }
    row.update(updates)
    return row


def test_nps_only_approved_broll_with_original_4k_video(monkeypatch):
    monkeypatch.setenv("NPS_API_KEY", "fake-key")
    monkeypatch.setenv("PURFFLE_NO_ATTRIBUTION", "1")
    reg = registry({"data": [nps_record()]})
    assert ProviderRegistry._nps_public_domain_credit("NPS/Staff", nps_record())
    assert len(reg._nps("ocean waves")) == 1, "NPS schema/rights gate filtered approved fixture"
    clips = reg.search("nps-video", "ocean waves")
    assert len(clips) == 1
    assert clips[0].source == "nps-video"
    assert clips[0].url.endswith("/4k.mp4")
    assert clips[0].duration == 9
    assert clips[0].extra["license"]["id"] == "PDM-1.0"
    assert clips[0].extra["license"]["attribution_required"] is False
    args, kwargs = reg.client.get.call_args
    assert args == ("https://developer.nps.gov/api/v1/multimedia/videos",)
    assert kwargs["headers"] == {"X-Api-Key": "fake-key"}
    assert kwargs["params"]["q"] == "ocean waves"
    assert kwargs["params"]["limit"] <= 20


@pytest.mark.parametrize("overrides", [
    {"credit": ""},
    {"credit": "© NPS"},
    {"credit": "Getty Images"},
    {"credit": "NPS, footage courtesy partner"},
    {"credit": "NPS/Staff", "copyright": "All rights reserved"},
    {"credit": "NPS/Staff", "isBRoll": False, "isVideoOnly": False},
    {"credit": "NPS/Staff", "permalinkUrl": "https://evil.example.com/video"},
    {"credit": "NPS/Staff", "versions": [{
        "url": "https://www.nps.gov/nps-audiovideo/audiovideo/low.mp4",
        "fileType": "video/mp4", "widthPixels": 640, "heightPixels": 360}]},
    {"credit": "NPS/Staff", "versions": [{
        "url": "https://attacker.example/nps-audiovideo/audiovideo/hd.mp4",
        "fileType": "video/mp4", "widthPixels": 1920, "heightPixels": 1080}]},
])
def test_nps_rejects_unproved_rights_or_bad_media(monkeypatch, overrides):
    monkeypatch.setenv("NPS_API_KEY", "fake-key")
    reg = registry({"data": [nps_record(**overrides)]})
    assert reg.search("nps-video", "ocean") == []


def test_nps_missing_key_skips_without_api_call(monkeypatch):
    monkeypatch.delenv("NPS_API_KEY", raising=False)
    reg = registry({"data": [nps_record()]})
    assert not reg.search("nps-video", "ocean")
    reg.client.get.assert_not_called()


def test_cover2_is_alias_if_primary_missing_not_a_new_provider(monkeypatch):
    monkeypatch.setenv("COVER2", "second-coverr-key")
    reg = registry({"hits": []})
    assert "coverr-video" in reg.enabled
    assert reg.search("coverr-video", "ocean") == []
    assert reg.client.get.call_args.kwargs["headers"] == {
        "x-api-key": "second-coverr-key"}
    assert "cover2-video" not in reg.providers
    monkeypatch.setenv("COVERR_API_KEY", "primary-key")
    assert reg.search("coverr-video", "ocean") == []
    assert reg.client.get.call_args.kwargs["headers"] == {
        "x-api-key": "primary-key"}


def test_coverr_unauthorized_never_tries_cover2(monkeypatch):
    monkeypatch.setenv("COVERR_API_KEY", "primary-key")
    monkeypatch.setenv("COVER2", "secondary-key")
    reg = registry()
    reg.client.get.side_effect = ProviderError("http_429", "quota")
    assert reg.search("coverr-video", "waves") == []
    assert reg.search("coverr-video", "other") == []
    assert reg.client.get.call_count == 1
    assert reg.client.get.call_args.kwargs["headers"] == {
        "x-api-key": "primary-key"}


def test_vecteezy_free_key_will_not_burn_downloads_or_require_description(monkeypatch):
    monkeypatch.setenv("VECTEEZY_API_KEY", "account-key")
    reg = registry({"resources": [{"id": "v1"}]})
    assert "vecteezy-video" not in reg.enabled
    assert reg.search("vecteezy-video", "waves") == []
    assert reg.events[-1]["status"] == "skipped"
    assert "attribution" in reg.events[-1]["detail"]
    reg.client.get.assert_not_called()


def test_no_manual_credit_rejects_licenses_requiring_attribution(monkeypatch):
    reg = registry()
    cc = Item("wikimedia-video", "cc", "video",
              "https://upload.wikimedia.org/one.webm", text="ocean wave")
    cc.extra["license"] = ProviderRegistry.license(
        "CC-BY-4.0", "https://creativecommons.org/licenses/by/4.0/",
        "A filmmaker", "https://commons.wikimedia.org/wiki/File:wave")
    free = Item("wikimedia-video", "free", "video",
                "https://upload.wikimedia.org/two.webm", text="ocean wave")
    free.extra["license"] = ProviderRegistry.license(
        "CC0-1.0", "https://creativecommons.org/publicdomain/zero/1.0/",
        "Public domain", "https://commons.wikimedia.org/wiki/File:free")
    reg._wikimedia = lambda query: [cc, free]
    monkeypatch.setenv("PURFFLE_NO_ATTRIBUTION", "1")
    assert [x.id for x in reg.search("wikimedia-video", "waves")] == ["free"]
    monkeypatch.setenv("PURFFLE_NO_ATTRIBUTION", "0")
    assert [x.id for x in reg.search("wikimedia-video", "waves")] == ["cc", "free"]
