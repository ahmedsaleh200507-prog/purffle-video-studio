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
import time
from urllib.parse import quote

from topic_footage import words

_CURRENT = ContextVar("purffle_science_evidence", default=None)
_REVIEW_FEEDBACK = ContextVar("purffle_science_review_feedback", default="")
_STOP = set("what why where when how which who does do is are can a an the to of in for on "
            "with from and or this that some have has do you your what happens makes "
            "warum wie was wann wo wer wieso weshalb ist sind die der das den dem "
            "ein eine einer und von zu im mit bei auf als er sie es".split())
# Generic title words may not justify an unrelated encyclopedia article.
# A title like "Wild China" cannot substantiate wilderness survival advice.
_WEAK_TITLE_TERMS = {"wild", "people", "night", "list", "show", "series",
                     "movie", "film", "strom", "nacht", "winter", "auto"}

_OFFICIAL = {
    "volcano_eruption": (
        "https://www.usgs.gov/faqs/how-do-volcanoes-erupt",
        "https://www.usgs.gov/programs/VHP/about-volcanoes",
    ),
    "iceberg_breakup": (
        "https://nsidc.org/learn/parts-cryosphere/ice-shelves/science-ice-shelves",
        "https://nsidc.org/learn/ask-scientist/how-ice-shelf-disintegration-different-calving",
    ),
    "whale_breaching": (
        "https://www.marinemammalcenter.org/news/your-visual-guide-to-whale-breaching-lunge-feeding-and-other-behaviors",
        "https://www.fisheries.noaa.gov/species/humpback-whale",
    ),
    "shark_ventilation": (
        "https://www.floridamuseum.ufl.edu/discover-fish/sharks/faq/",
        "https://ocean.si.edu/ocean-life/sharks-rays/sharks",
    ),
    "sea_turtle_rest": (
        "https://www.fisheries.noaa.gov/national/outreach-and-education/fun-facts-about-terrific-sea-turtles",
        "https://www.fisheries.noaa.gov/feature-story/10-tremendous-turtle-facts",
    ),
    "waterfall_freezing": (
        "https://www.cambridge.org/core/journals/journal-of-glaciology/article/waterfall-ice-formation-structure-and-evolution/40B6A986541E1A24626192F68A5EED2F",
        "https://www.nps.gov/yose/planyourvisit/frazilice.htm",
    ),
    "steel_ship_buoyancy": (
        "https://openstax.org/books/university-physics-volume-1/pages/14-4-archimedes-principle-and-buoyancy",
        "https://manoa.hawaii.edu/exploringourfluidearth/physical/navigation-and-transportation/transportation-and-ship-design",
    ),
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


def _blue_sky_question(topic: str) -> bool:
    """Identify questions about the sky's colour, not companies or songs.

    Used only for evidence retrieval. It does not assert a scientific fact.
    """
    value = str(topic).casefold()
    return bool(
        re.search(r"\bsky\b.{0,40}\bblue\b|\bblue\b.{0,40}\bsky\b", value)
        or re.search(r"\bhimmel\b.{0,40}\bblau\w*\b|\bblau\w*\b.{0,40}\bhimmel\b", value)
    )


def _blue_sky_scientific_article(title: str, extract: str) -> bool:
    """Don't mistake 'Blue Sky Studios' or a song for optics references."""
    label = str(title).casefold().strip()
    # The scientist's biography and nonlinear laboratory optics are not
    # sources explaining the scattering that colours the daytime sky.
    if re.search(r"hyper[\s\-–—]*rayleigh|john william strutt|baron rayleigh", label):
        return False
    if re.search(r"rayleigh|scattering|streuung|atmospher|atmosphär|optics|optik|himmelsblau|diffuse sky radiation", label):
        return True
    # The bare Sky/Himmel encyclopaedia entries may contain the physical
    # explanation, whereas 'Blue Sky Studios' is not a sky article.
    return label in {"sky", "himmel"} and bool(
        re.search(r"rayleigh|scatter|streuung", str(extract).casefold()))


@contextmanager
def use_review_feedback(feedback):
    """One redraft receives only bounded, independently rejected claim text."""
    token = _REVIEW_FEEDBACK.set(str(feedback or "")[:900])
    try:
        yield
    finally:
        _REVIEW_FEEDBACK.reset(token)


def review_feedback():
    return _REVIEW_FEEDBACK.get()


def rejected_claim_feedback(report_path, script):
    """Build safe revision guidance from unsupported scenes in a QA report.

    No provider descriptions, model-generated reviewer reasons, excerpts,
    URLs or potentially sensitive values are copied into the prompt.
    """
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    if report.get("state") != "failed":
        return ""
    scenes = list(getattr(script, "scenes", []) or [])
    messages = []
    seen = set()
    for row in report.get("scene_checks", []):
        if not isinstance(row, dict) or row.get("supported") is not False:
            continue
        index = row.get("scene")
        if type(index) is not int or index < 1 or index > len(scenes) or index in seen:
            continue
        seen.add(index)
        # Use the draft's own narration instead of untrusted reviewer strings.
        old = re.sub(r"[^\w äöüÄÖÜß,.!?;:'-]", " ",
                     str(scenes[index - 1].narration))[:170]
        old = re.sub(r"\s+", " ", old).strip()
        messages.append(
            f"Scene {index}: the previous text was not supported by the provided "
            f"reference excerpts: '{old}'. Do not repeat this unsupported claim; "
            "replace it with a simpler, different fact explicitly present in "
            "the reference text. Preserve the topic and complete explanation.")
    return "\n".join(messages)[:900]


def _search_text(topic: str) -> str:
    # Use the relevant mechanism as a retrieval term for recurring questions.
    # These words are search queries only, not facts asserted in narration.
    subject = words(topic)
    if _blue_sky_question(topic):
        return ("Rayleigh-Streuung" if re.search(
            r"\bhimmel\b", str(topic).casefold()) else
            "Rayleigh scattering")
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


def _fallback_search_queries(topic: str, language: str) -> tuple[str, ...]:
    """Bounded real-source lookups for inflected educational subjects.

    These are only SEARCH WORDS, never citations or made-up scientific facts.
    Every result must still return a real Wikipedia excerpt and pass the
    original independent paragraph-level scientific review.
    """
    text = str(topic).casefold()
    queries = []
    if _blue_sky_question(topic):
        queries += (["Rayleigh scattering", "Diffuse sky radiation", "Atmospheric optics"]
                    if language == "en" else
                    ["Rayleigh-Streuung", "Himmelsblau", "Atmosphärische Optik"])
    if language == "en":
        if "octopus" in text or "octopuses" in text:
            queries += ["octopus", "octopus anatomy"]
        if "humpback" in text or "whale" in text:
            queries += ["humpback whale"]
        if ("freezing" in text or "cold" in text) and (
                "surviv" in text or "wild" in text or "wilderness" in text):
            queries += ["Hypothermia", "Thermal insulation"]
        if "rocket" in text and ("launch" in text or "engine" in text) and (
                "smoke" in text or "cloud" in text or "plume" in text):
            queries += ["Rocket engine", "Rocket exhaust", "Water deluge system"]
    else:
        if "nilkrokodil" in text or "salzwasserkrokodil" in text:
            queries += ["Nilkrokodil", "Leistenkrokodil", "Krokodile"]
        if "bergzieg" in text:
            queries += ["Schneeziege", "Alpensteinbock"]
        if "winterwald" in text or "wintertiere" in text:
            queries += ["Winterschlaf", "Winterruhe"]
        if "pinguin" in text:
            queries += ["Pinguine"]
        if "robben" in text or "robbe" in text:
            queries += ["Robben"]
        if ("kuhmist" in text or "gülle" in text or "guelle" in text
                or ("mist" in text and "strom" in text)):
            queries += ["Biogas", "Biogasanlage"]
        if ("autoscheib" in text or "windschutzscheib" in text
                or ("autoglas" in text and "frier" in text)) and (
                "frier" in text or "eis" in text or "frost" in text):
            queries += ["Reif (Niederschlag)", "Raureif", "Taupunkt"]
    return tuple(dict.fromkeys(queries))[:4]


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
    queries = tuple(dict.fromkeys((
        search, *_fallback_search_queries(topic, lang)
    )))
    # Exact lexical overlap with the actual query prevents collecting a
    # loosely related encyclopedia article and pretending it proves the user
    # question. A plural/compound synonym can now reach the real article.
    collected = []
    # A transient failure on the first query must not prevent valid backup
    # source queries. Still fail closed if no real reference is returned.
    source_errors = []
    for search_query in queries:
        try:
            response = client.get(
                endpoint,
                params={"action": "query", "generator": "search",
                        "gsrsearch": search_query, "gsrnamespace": 0, "gsrlimit": 5,
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
        except (requests.RequestException, OSError, ValueError,
                TimeoutError, RuntimeError) as exc:
            source_errors.append(type(exc).__name__)
            continue
        if not isinstance(document, dict):
            source_errors.append("invalid_response")
            continue
        pages = (document.get("query") or {}).get("pages") or []
        if not isinstance(pages, list):
            pages = []
        search_terms = words(search_query) - _STOP
        for page in pages:
            title = str(page.get("title") or "").strip()
            extract = re.sub(r"\s+", " ", str(page.get("extract") or "")).strip()
            if (not title or page.get("missing") or len(extract) < 180
                    or "may refer to:" in extract[:150].casefold()):
                continue
            title_terms = words(title)
            overlap = title_terms & search_terms
            if lang == "de" and not overlap:
                overlap = {t for t in title_terms for q in search_terms
                           if len(t) >= 4 and (q.startswith(t) or t.startswith(q))
                           and abs(len(t) - len(q)) <= 3}
            if lang == "en" and not overlap:
                overlap = {t for t in title_terms for q in search_terms
                           if len(t) >= 5 and (q.startswith(t) or t.startswith(q))
                           and abs(len(t) - len(q)) <= 3}
            # Single generic words are insufficient anchors. In particular,
            # "Wild China" / episode lists must not be accepted for advice
            # about surviving a freezing night.
            if not overlap or overlap <= _WEAK_TITLE_TERMS:
                continue
            # For a blue-sky physics question, title-token overlap alone
            # wrongly accepted the song 'Mr. Blue Sky' and animation company
            # 'Blue Sky Studios'. Only optics/atmospheric science entries
            # may underpin a factual narration about scattering.
            if _blue_sky_question(topic) and not _blue_sky_scientific_article(title, extract):
                continue
            collected.append((len(overlap), title, extract[:3100]))
        # One directly relevant source is enough to get a screenable draft.
        # No broad search fan-out once a real independent reference is present.
        if collected:
            break
    collected.sort(key=lambda p: (-p[0], p[1]))
    seen_titles = set()
    ranked = []
    for score, title, extract in collected:
        if title.casefold() not in seen_titles:
            ranked.append((score,title,extract))
            seen_titles.add(title.casefold())
    sources = tuple({
        "id": f"wiki-{i}", "title": title,
        "url": f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='()')}",
        "tier": "community_edited_reference",
        "license": "CC BY-SA (see linked article and its history)",
        "excerpt": excerpt,
    } for i, (_, title, excerpt) in enumerate(ranked[:2], 1))
    if not sources:
        suffix = (f"; retrieval_errors={','.join(source_errors[:3])}"
                  if source_errors else "")
        raise RuntimeError(
            "science_sources_unavailable: no topic-relevant reference extracts" + suffix)
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


def _validate_model_scene_checks(checks, scenes, bundle):
    """Validate every model assertion against literal, source-owned excerpts.

    A JSON schema match is not sufficient: quotes must be exact excerpts of
    a real retrieved source. Unsupported/partially supported scenes stay false.
    """
    if not isinstance(checks, list) or len(checks) != len(scenes):
        raise ValueError("review returned incomplete scene checks")
    source_by_id = {source["id"]: source for source in bundle.sources}
    accepted = []
    for i, item in enumerate(checks, 1):
        if (not isinstance(item, dict) or type(item.get("scene")) is not int
                or item["scene"] != i):
            raise ValueError("review returned invalid scene index")
        source = source_by_id.get(item.get("source_id"))
        quote = str(item.get("quote") or "").strip()
        supported = item.get("supported") is True
        anchored = (
            source is not None and 20 <= len(quote) <= 300
            and _normalize_quote(quote) in _normalize_quote(source.get("excerpt", "")))
        narration = str(scenes[i - 1].narration).casefold()
        absolutes = re.findall(r"\b(always|never|only|immer|niemals|nur)\b", narration)
        if absolutes and not all(word in quote.casefold() for word in absolutes):
            anchored = False
        accepted.append({
            "scene": i, "source_id": str(item.get("source_id") or "")[:40],
            "supported": supported and anchored,
            "quote": quote[:180] if anchored else "",
            "reason": str(item.get("reason") or "")[:180],
        })
    return accepted


def _strict_science_review_json(llm, system, prompt, schema):
    """Evidence-review-only strict Groq JSON Schema, never silent JSON downgrade.

    Pinned upstream's OpenAICompatible.complete() silently switches from
    json_schema to json_object on HTTP 400/422, so required `supported`
    can disappear without the caller noticing. Send a dedicated strict
    request to the documented Groq endpoint for this one safety-critical
    reviewer. Fail closed on non-200, invalid JSON, or incomplete results;
    no source citation checks or narration validation are bypassed.
    """
    selected = next((p for p in getattr(llm, "providers", ())
                     if getattr(p, "name", "") == "groq"
                     and getattr(p, "model", "") in (
                         "openai/gpt-oss-20b", "openai/gpt-oss-120b")), None)
    # Mock clients and non-Groq providers retain their preexisting behavior.
    # The live Groq science-review path must never silently downgrade.
    if selected is not None and os.getenv("GROQ_API_KEY"):
        import requests
        payload = {
            "model": selected.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "purffle_science_review",
                    "strict": True,
                    "schema": schema,
                },
            },
            "max_completion_tokens": 4096,
            "temperature": 0.0,
        }
        # A transient free-tier TPM 429 is not a science failure. Keep the
        # *same* review request and wait for its real token-window reset rather
        # than redrafting the entire story or buying another API. At most two
        # bounded waits; never spin or retry a different HTTP error.
        response = None
        for rate_attempt in range(3):
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload,
                    headers={"Authorization": "Bearer " + os.environ["GROQ_API_KEY"],
                             "Content-Type": "application/json"},
                    timeout=(10, 90))
            except requests.RequestException:
                raise RuntimeError("science_review_unavailable: strict_groq_network") from None
            if response.status_code != 429 or rate_attempt == 2:
                break
            # Read only a bounded numerical delay from the server; never copy
            # API response bodies (which can reveal account identifiers) to
            # application logs or artifacts. Cap each pause at 65 seconds.
            retry_after = getattr(response, "headers", {}).get("Retry-After", "")
            try:
                seconds = float(retry_after)
            except (TypeError, ValueError):
                seconds = 0
            if not (0 < seconds <= 65):
                seconds = 0
                try:
                    message = str(response.json().get("error", {}).get("message", ""))
                    found = re.search(
                        r"try again in\\s+([0-9]+(?:\\.[0-9]+)?)s", message, re.I)
                    if found:
                        seconds = float(found.group(1))
                except (ValueError, TypeError, AttributeError, KeyError):
                    pass
            wait = min(65, max(1, seconds + 1)) if seconds > 0 else 20
            print(f"[SCIENCE REVIEW] Free Groq token limit; waiting {wait:.1f}s "
                  f"before retry {rate_attempt + 1}/2", flush=True)
            time.sleep(wait)
        # Do not echo arbitrary provider error bodies (which may contain
        # prompts or account identifiers), HTTP headers or auth details.
        if response.status_code != 200:
            raise RuntimeError(
                "science_review_unavailable: strict_groq_http_"
                + str(int(response.status_code))) from None
        try:
            reply = response.json()["choices"][0]["message"]["content"]
            result = json.loads(reply)
        except (ValueError, KeyError, IndexError, TypeError):
            raise RuntimeError("science_review_unavailable: strict_groq_invalid_json") from None
        if not isinstance(result, dict):
            raise RuntimeError("science_review_unavailable: strict_groq_invalid_object")
        return result
    return llm.complete_json(system, prompt, schema)


def _review_scenes_individually(llm, system, source_text, scenes):
    """Last-resort smaller JSON review if a large array is repeatedly malformed.

    This NEVER bypasses the independent source-quote verifier. It only changes
    the JSON output shape to reduce model formatting failures.
    """
    properties = {
        "supported": {"type": "boolean"}, "source_id": {"type": "string"},
        "quote": {"type": "string"}, "reason": {"type": "string"}}
    schema = {
        "type": "object", "properties": properties,
        "required": list(properties), "additionalProperties": False}
    output = []
    for i, scene in enumerate(scenes, 1):
        answer = _strict_science_review_json(
            llm,
            system + " Review exactly ONE scene. Return ONE JSON object, not an array.",
            source_text + f"\n\nNARRATION TO CHECK:\nSCENE {i}: {scene.narration}",
            schema)
        # Groq's JSON-object mode is not strict JSON-schema mode. Even for
        # a one-scene schema it may wrap the answer in {"checks": [{...}]}.
        # Unwrap ONLY when it contains exactly one scene, with the expected
        # index. Never borrow a quoted source from a different scene.
        if isinstance(answer, dict) and isinstance(answer.get("checks"), list):
            rows = answer["checks"]
            if len(rows) != 1 or not isinstance(rows[0], dict):
                raise ValueError("single-scene review returned wrong number of checks")
            answer = rows[0]
        if not isinstance(answer, dict):
            raise ValueError("single-scene review did not return a JSON object")
        index = answer.get("scene", i)
        if str(index) != str(i):
            raise ValueError("single-scene review returned wrong scene index")
        if type(answer.get("supported")) is not bool:
            raise ValueError("single-scene review did not supply a verdict")
        # Never interpret an omitted quote or verdict as evidence in favour:
        # missing data become an explicit unsupported claim, not success.
        normalized = {
            "scene": i,
            "supported": answer.get("supported") is True,
            "source_id": str(answer.get("source_id") or ""),
            "quote": str(answer.get("quote") or ""),
            "reason": str(answer.get("reason") or "review did not supply evidence"),
        }
        output.append(normalized)
    return output


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
        if kind in (
                "ocean_waves", "ocean_glow_bioluminescence", "lava_ocean_entry",
                "northern_lights_dance", "steel_ship_buoyancy",
                "lightning_thunder_delay",
                "volcano_eruption", "iceberg_breakup", "whale_breaching",
                "shark_ventilation", "sea_turtle_rest", "waterfall_freezing",
                "northern_lights_glow", "mirror_condensation",
                "volcanic_island", "hurricane_eye"):
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
        "checks": {"type": "array",
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
        "in the cited reference. A clearly signalled visual metaphor such as "
        "'the lights seem to dance' is not a scientific causal claim: do not "
        "reject it just because the source uses different descriptive words. "
        "Every factual mechanism and scientific assertion still requires "
        "explicit support. Return JSON only. If supported, quote a short "
        "verbatim excerpt from the provided source (at least 20 characters). "
        "Do NOT fabricate citations or text. Reject unsupported claims.")
    source_text = evidence_prompt(bundle)
    script_text = "\n".join(f"SCENE {i}: {x.narration}"
                            for i, x in enumerate(scenes, 1))
    try:
        # The primary bulk review uses a bounded JSON array. If repeated
        # valid-HTTP replies have malformed shape, retry once with small,
        # single-scene objects. No unverified citation can pass either path.
        accepted = None
        for review_attempt in range(3):
            try:
                result = _strict_science_review_json(
                    llm, system, source_text + "\n\nNARRATION TO CHECK:\n" + script_text, schema)
                checks = result.get("checks") if isinstance(result, dict) else None
                accepted = _validate_model_scene_checks(checks, scenes, bundle)
                break
            except (ValueError, TypeError, KeyError):
                if review_attempt == 2:
                    checks = _review_scenes_individually(
                        llm, system, source_text, scenes)
                    accepted = _validate_model_scene_checks(checks, scenes, bundle)
                    break
                time.sleep(2 * (review_attempt + 1))
        if not all(row["supported"] for row in accepted):
            _report(report, bundle, "failed", checks=accepted,
                    error="source passage cannot substantiate all scene claims")
            raise RuntimeError("science_claim_unverified: unsupported narration scene")
        _report(report, bundle, "model_screened_reference", checks=accepted)
    except RuntimeError as exc:
        if str(exc).startswith("science_review_unavailable:"):
            _report(report, bundle, "failed",
                    error=str(exc)[:150])
        raise
    except (ValueError, TypeError, KeyError) as exc:
        # A reviewer unable to return a valid structure is NOT evidence that
        # the script's science is wrong. Distinguish this infrastructure error
        # from actual unsupported claims; do not burn quota redrafting.
        # Only report our own fixed structural labels. Never expose an LLM
        # response body, API key, provider URL, or arbitrary model text.
        known_structure_errors = {
            "review returned incomplete scene checks",
            "review returned invalid scene index",
            "single-scene review returned wrong number of checks",
            "single-scene review did not return a JSON object",
            "single-scene review returned wrong scene index",
            "single-scene review did not supply a verdict",
        }
        safe_detail = (str(exc) if str(exc) in known_structure_errors
                       else type(exc).__name__)
        _report(report, bundle, "failed",
                error=f"reviewer JSON unavailable: {safe_detail}")
        raise RuntimeError("science_review_unavailable: invalid_model_json") from None
    except Exception as exc:
        _report(report, bundle, "failed",
                error=f"source-grounded review unavailable: {type(exc).__name__}")
        raise RuntimeError("science_review_unavailable: model_error") from None
