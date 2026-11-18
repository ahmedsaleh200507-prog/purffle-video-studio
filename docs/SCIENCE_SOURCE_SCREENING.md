# V3 science-source screen (incremental)

The successful volcanic-island production and pinned male Piper voices are unchanged.

## What is new
- Footage selection **still occurs before script generation**.
- Before drafting an unfamiliar general-science topic, the worker searches the
  **official Wikimedia API** for at most two topic-matched encyclopedia leads.
  This is free and keyless; network problems are reported as explicit failure,
  not fabricated sources. `de|` uses German-language references.
- The scriptwriter sees the independently obtained text. After drafting, an
  additional model screening pass must cite a **literal 20–300 character
  quotation** from an actual returned source for every narration scene.
  Fake source IDs, fabricated source snippets, unsupported or ambiguous scene
  claims, and missing responses fail **before Piper creates audio**.
- Each worker writes `science-report.json` with source URLs, source tiers,
  scene-level screen results and a warning about the method's limitations.
  The source text itself is not copied into the final ZIP.
- Previously editor-reviewed NOAA/USGS/NPS narration for recognized hurricane,
  volcanic-island and repeated-lightning explainers stays prioritized and is
  labelled `curated_editor_reviewed`.
- The existing quantitative-claim block also runs before audio.

## Scientific limits (do not overclaim)
Wikipedia is **community edited**, not a peer-reviewed source. A language model
checking a paragraph is fallible and may miss ungrounded logic, negation,
misleading causal relationships, or omissions. The success state for new topics
is `model_screened_reference`, *never* `independently_fact_checked`.
Editorial review and stronger primary/agency source retrieval remain goals.
The method can reject legitimate stories when the references or model are
unavailable. It intentionally never repairs a false claim by making one up.

## Output and failures
- `science_sources_unavailable`: no reliable independent reference extract.
- `science_claim_unverified`: reviewer cannot anchor a scene to the source.
- Failed workers retain a `science-report.json` when the source/review stage
  is reached, and normal ZIP aggregation continues to include other successes.
- The legacy path `PURFFLE_MEDIA_FIRST=0` is not converted into a vetted
  source-grounded pipeline.

## API references
- https://www.mediawiki.org/wiki/API:Search_and_discovery
- https://www.mediawiki.org/wiki/Extension:TextExtracts
- https://www.mediawiki.org/wiki/API:Get_the_contents_of_a_page

## Verification
`python -m pytest -q tests/test_science_sources.py` and the existing
full regression suite. Real-world claims, upstream API availability, and
10/10 production must be verified separately by GitHub Actions; CI unit tests
alone do not establish these outcomes.
