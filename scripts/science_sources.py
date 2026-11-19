"""Source-grounded *screening* for general educational Shorts.

Source anchors are independently fetched before drafting and before speech.
Wikipedia is secondary/community-edited context, NOT a scientific authority.
Model support judgements are fallible, so reports explicitly say screened,
never scientifically verified. Editor-reviewed official dossiers remain first.
No paid external research API is used; no sources means no publication claim.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from urllib.parse import quote

from topic_footage import words

_CURRENT = ContextVar("purffle_science_evidence", default=None)
_STOP = set("what why where when how which who does do is are can a an the to of in for on "
            "with from and or this that some have has do you your what happens makes "
            "warum wie was wann wo wer wieso weshalb ist sind die der das den dem "
            "ein eine einer und von zu im mit bei auf als er sie es".split())
_OFFICIAL = {
    "lightning_thunder_delay": (
        "https://www.nesdis.noaa.gov/about/k-12-education/severe-weather/what-causes-lightning-and-thunder",
        "https://www.nssl.noaa.gov/education/svrwx101/lightning/",
    ),
    "northern_lights_dance": (
        "https://www.spaceweather.gov/phenomena/aurora",
        "https://science.nasa.gov/sun/auroras/",
    ),
    "northern_lights_glow": (
        "https://www.spaceweather.gov/phenomena/aurora",
        "https://science.nasa.gov/sun/auroras/",
    ),
    "ocean_waves": (
        "https://oceanexplorer.noaa.gov/ocean-fact/waves/",
        "https://oceanservice.noaa.gov/education/tutorial_currents/03coastal1.html",
        "https://www.ndbc.noaa.gov/education/pacwave.shtml",
    ),
    "lava_ocean_entry": (
        "https://www.usgs.gov/observatories/hvo/science/lava-entering-ocean",
        "https://www.usgs.gov/news/volcano-watch-what-happens-when-lava-flows-sea",
    ),
    "ocean_glow_bioluminescence": (
        "https://oceanexplorer.noaa.gov/ocean-fact/bioluminescence/",
        "https://ocean.si.edu/ocean-life/six-ways-see-ocean-ocean-bioluminescence",
        "https://oceanservice.noaa.gov/facts/biolum.html",
    ),
    "mirror_condensation": (
        "https://www.nesdis.noaa.gov/about/k-12-education/atmosphere/what-humidity",
        "https://scied.ucar.edu/learning-zone/how-weather-works/humidity",
    ),
    "volcanic_island": (
        "https://www.nps.gov/subjects/geology/plate-tectonics-oceanic-hotspots.htm",
        "https://www.usgs.gov/observatories/hvo/evolution-hawaiian-volcanoes",
    ),
    "hurricane_eye": (
        "https://www.noaa.gov/jetstream/tropical/tropical-cyclone-introduction/tropical-cyclone-structure",
        "https://www.aoml.noaa.gov/hrd/tcfaq/A11.html?print=yes",
    ),
    "lightning_repeated": (
        "https://www.nssl.noaa.gov/education/svrwx101/lightning/faq/",
        "https://www.weather.gov/safety/lightning-myths",
    ),
}

@dataclass(frozen=True)
class Evidence:
    topic: str
    sources: tuple[dict, ...]
    method: str
    # Every source must have a stable ID, URL, title and excerpt or official provenance.


def active_evidence():
    return _CURRENT.get()


@contextmanager
def use_evidence(bundle):
    token = _CURRENT.set(bundle)
    try:
        yield bundle
    finally:
        _CURRENT.reset(token)


def _search_text(topic: str) -> str:
    # Use the relevant mechanism as a retrieval term for recurring questions.
    # These words are search queries only, not facts asserted in narration.
    subject = words(topic)
    if {"steel", "ship"} <= subject and "float" in subject:
        return "ship buoyancy displacement"
    if "shark" in subject and ("swim" in subject or "swimming" in subject):
        return "shark ram ventilation breathing"
    if "waterfall" in subject and any(x in topic.casefold()
                                      for x in ("freez", "frozen", "ice")):
        return "waterfall frozen ice"
    # Keep the actual key terms, not invented scientific hypotheses.
    terms = [w for w in re.findall(r"[\wäöüß]+", str(topic).casefold())
             if len(w) > 2 and w not in _STOP]
    return " ".join(terms[:7])[:130]


def _official_kind(topic):
    from fact_checked_topics import _lightning_repeated_topic, verified_documentary_kind
    if _lightning_repeated_topic(topic):
        return "lightning_repeated"
    return verified_documentary_kind(topic)


def discover_evidence(topic: str, language="en", *, session=None) -> Evidence:
    """Fail closed if no source can be retrieved; no model-generated URLs.

    English/German Wikipedia lead paragraphs are bounded reference context
    rather than interchangeable official research papers. Page URLs are built
    only from results of the fixed public API host.
    """
    kind = _official_kind(topic)
    if kind:
        return Evidence(str(topic), tuple({
            "id": f"official-{i}", "title": kind.replace("_", " "),
            "url": url, "tier": "editor_reviewed_official_dossier",
        } for i, url in enumerate(_OFFICIAL[kind], 1)), "curated_editor_reviewed")
    search = _search_text(topic)
    if not search:
        raise RuntimeError("science_sources_unavailable: topic has no usable search terms")
    import requests
    lang = "de" if str(language).lower().startswith("de") else "en"
    endpoint = f"https://{lang}.wikipedia.org/w/api.php"
    client = session or requests.Session()
    try:
        response = client.get(
            endpoint,
            params={"action": "query", "generator": "search",
                    "gsrsearch": search, "gsrnamespace": 0, "gsrlimit": 5,
                    "prop": "extracts", "exintro": 1, "explaintext": 1,
                    "exchars": 3200, "format": "json", "formatversion": 2},
            headers={"User-Agent": "PurffleVideoStudio/3.0 (+https://github.com/ahmedsaleh200507-prog/purffle-video-studio)",
                     "Accept": "application/json"},
            timeout=(6, 14), allow_redirects=False, stream=True)
        with response:
            if response.status_code != 200:
                raise RuntimeError(f"science_source_http_{response.status_code}")
            if int(response.headers.get("Content-Length", "0")) > 180000:
                raise RuntimeError("science_source_oversized")
            chunks, count = [], 0
            for chunk in response.iter_content(16384):
                count += len(chunk)
                if count > 180000:
                    raise RuntimeError("science_source_oversized")
                chunks.append(chunk)
        document = json.loads(b"".join(chunks))
    except (requests.RequestException, OSError, ValueError) as exc:
        raise RuntimeError(f"science_sources_unavailable: {type(exc).__name__}") from None
    if not isinstance(document, dict):
        raise RuntimeError("science_sources_unavailable: invalid response")
    pages = (document.get("query") or {}).get("pages") or []
    if not isinstance(pages, list):
        pages = []
    topic_terms = words(search) - _STOP
    ranked = []
    for page in pages:
        title = str(page.get("title") or "").strip()
        extract = re.sub(r"\s+", " ", str(page.get("extract") or "")).strip()
        if (not title or page.get("missing") or len(extract) < 180
                or "may refer to:" in extract[:150].casefold()):
            continue
        title_terms = words(title)
        overlap = title_terms & topic_terms
        if lang == "de" and not overlap:
            # German plural/case inflections: Insel / Inseln, Berg / Bergen.
            # Only tiny suffix differences count; broad semantic pivots do not.
            overlap = {t for t in title_terms for q in topic_terms
                       if len(t) >= 4 and (q.startswith(t) or t.startswith(q))
                       and abs(len(t) - len(q)) <= 3}
        if not overlap:
            continue
        ranked.append((len(overlap), title, extract[:3100]))
    ranked.sort(key=lambda p: (-p[0], p[1]))
    sources = tuple({
        "id": f"wiki-{i}", "title": title,
        "url": f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='()')}",
        "tier": "community_edited_reference",
        "license": "CC BY-SA (see linked article and its history)",
        "excerpt": excerpt,
    } for i, (_, title, excerpt) in enumerate(ranked[:2], 1))
    if not sources:
        raise RuntimeError("science_sources_unavailable: no topic-relevant reference extracts")
    return Evidence(str(topic), sources, "model_screened_reference")


def evidence_prompt(bundle: Evidence) -> str:
    if bundle.method == "curated_editor_reviewed":
        return ("Use the editor-reviewed factual narration for this recognized "
                "documentary topic. Do not introduce additional factual claims.")
    lines = [
        "INDEPENDENT REFERENCE CONTEXT FOR EDUCATIONAL NARRATION:",
        "These excerpts are community-edited encyclopedia reference text, not "
        "proof of all scientific claims. Use only conservative facts specifically "
        "supported by this text. DO NOT invent an anecdote, person, study, "
        "historical case, measurement, causal explanation, quote, or conclusion.",
        "Do not present source descriptions as direct video observations.",
        "OUTPUT REQUIREMENT: Narrate without digits, numerical measurements, "
        "precise heights, distances, speeds, dates, percentages or other quantities. "
        "Use qualitative wording even when a reference has exact figures. "
        "Every factual assertion must be supported by the provided excerpts.",
        "If uncertain, give a simpler statement directly supported by the excerpts.",
    ]
    for source in bundle.sources:
        lines.extend([f"[{source['id']}] {source['title']} — {source['url']}",
                      source["excerpt"]])
    return "\n".join(lines)


def _normalize_quote(text):
    return re.sub(r"\s+", " ", str(text).strip()).casefold()


def _report(path: Path, bundle: Evidence | None, state: str, *, checks=(), error=""):
    payload = {
        "state": state,
        "method": bundle.method if bundle else "none",
        "warning": ("Reference matching and AI assessment do NOT establish "
                    "independent scientific truth; editorial review is advisable."),
        "sources": [{k: v for k, v in item.items() if k != "excerpt"}
                    for item in bundle.sources] if bundle else [],
        "scene_checks": list(checks),
    }
    if error:
        payload["error"] = error[:400]
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def write_source_failure(reason: str, path=None):
    """Keep an honest report even when retrieval fails before drafting."""
    _report(Path(path or os.getenv("SCIENCE_REPORT", "science-report.json")),
            None, "failed", error=reason)


def screen_narration(script, bundle: Evidence, llm, *, path=None):
    """Check a cited passage per scene; a missing/mismatched quote blocks TTS.

    The verifier is an LLM (not a scientific oracle). Requiring a literal
    independent source quotation makes source fabrication detectable; authors
    should still inspect the report before publishing a general-science claim.
    """
    report = Path(path or os.getenv("SCIENCE_REPORT", "science-report.json"))
    if bundle.method == "curated_editor_reviewed":
        # Curated mode is reserved for exact, fixed sentences tied to official
        # source dossiers. A caller must never smuggle an arbitrary Groq
        # narration past the independent model/source review gate.
        from fact_checked_topics import (
            verified_documentary_kind, ground_verified_documentary)
        kind = verified_documentary_kind(bundle.topic)
        if kind in ("ocean_waves", "ocean_glow_bioluminescence", "lava_ocean_entry", "northern_lights_dance"):
            scenes = getattr(script, "scenes", [])
            spoken = [str(x.narration) for x in scenes]
            approved_variants = [
                [x["narration"] for x in ground_verified_documentary(
                    {}, bundle.topic, language, scene_count=len(scenes))["scenes"]]
                for language in ("en", "de")
            ]
            if spoken not in approved_variants or not (
                    len(bundle.sources) >= 2 and
                    all(s["url"].startswith("https://") and
                        s.get("tier") == "editor_reviewed_official_dossier"
                        for s in bundle.sources)):
                _report(report, bundle, "failed",
                        error="curated narration differs from official-source-backed dossier")
                raise RuntimeError("science_claim_unverified: nonapproved curated factual claims")
        _report(report, bundle, "curated_editor_reviewed")
        return
    scenes = getattr(script, "scenes", [])
    if not scenes:
        _report(report, bundle, "failed", error="empty narration")
        raise RuntimeError("science_claim_unverified: no narration")
    if llm is None:
        _report(report, bundle, "failed", error="no independent model review")
        raise RuntimeError("science_claim_unverified: model reviewer missing")
    schema = {"type": "object", "properties": {
        "checks": {"type": "array", "minItems": len(scenes), "maxItems": len(scenes),
            "items": {"type": "object", "properties": {
                "scene": {"type": "integer"}, "supported": {"type": "boolean"},
                "source_id": {"type": "string"}, "quote": {"type": "string"},
                "reason": {"type": "string"}},
                "required": ["scene", "supported", "source_id", "quote", "reason"],
                "additionalProperties": False}}
        }, "required": ["checks"], "additionalProperties": False}
    system = (
        "You are a conservative source-grounding reviewer. Check each narration "
        "scene for EVERY scientific and causal claim. Reject when even one "
        "claim is absent, contradictory, only indirectly implied, or ambiguous "
        "in the cited reference. Return JSON only. If supported, quote a short "
        "verbatim excerpt from the provided source (at least 20 characters). "
        "Do NOT fabricate citations or text. Reject unsupported claims.")
    source_text = evidence_prompt(bundle)
    script_text = "\n".join(f"SCENE {i}: {x.narration}"
                            for i, x in enumerate(scenes, 1))
    try:
        result = llm.complete_json(
            system, source_text + "\n\nNARRATION TO CHECK:\n" + script_text, schema)
        checks = result.get("checks") if isinstance(result, dict) else None
        if not isinstance(checks, list) or len(checks) != len(scenes):
            raise ValueError("review returned incomplete scene checks")
        sources_by_id = {s["id"]: s for s in bundle.sources}
        accepted = []
        for i, item in enumerate(checks, 1):
            if not isinstance(item, dict) or type(item.get("scene")) is not int or item["scene"] != i:
                raise ValueError("review returned invalid scene index")
            source = sources_by_id.get(item.get("source_id"))
            quote = str(item.get("quote") or "").strip()
            supported = item.get("supported") is True
            anchored = (source is not None and 20 <= len(quote) <= 300
                        and _normalize_quote(quote) in _normalize_quote(source["excerpt"]))
            # Simple literal checks supplement, but never replace, the semantic
            # review: 'always' and 'never' cannot be inferred from hedged text.
            narration = str(scenes[i-1].narration).casefold()
            absolutes = re.findall(r"\b(always|never|only|immer|niemals|nur)\b", narration)
            if absolutes and not all(word in quote.casefold() for word in absolutes):
                anchored = False
            accepted.append({
                "scene": i, "source_id": str(item.get("source_id") or "")[:40],
                "supported": supported and anchored,
                "quote": quote[:180] if anchored else "",
                "reason": str(item.get("reason") or "")[:180],
            })
        if not all(row["supported"] for row in accepted):
            _report(report, bundle, "failed", checks=accepted,
                    error="source passage cannot substantiate all scene claims")
            raise RuntimeError("science_claim_unverified: unsupported narration scene")
        _report(report, bundle, "model_screened_reference", checks=accepted)
    except RuntimeError:
        raise
    except Exception as exc:
        _report(report, bundle, "failed",
                error=f"source-grounded review unavailable: {type(exc).__name__}")
        raise RuntimeError(f"science_claim_unverified: {type(exc).__name__}") from None
