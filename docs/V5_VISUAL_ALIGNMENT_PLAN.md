# Visual-to-narration alignment: acceptance plan (V5)

Purpose: a *technically valid* MP4 must not be reported as a visually accurate educational video without scene-level visual evidence.

## Root cause (real 2026-11-23 proof)
- Narration "This diffuse radiation is what we see when we look upward" was paired by the writer with object="eyes", main_character="person", and query="person looking at sky". A face close-up was then a good match for the *wrong plan*.
- Narration about light interacting with air used sunset and person-walking footage; CLIP measured broad subject relatedness, not whether the frame conveyed the scientific statement.
- Non-event ("illustrative_subject") scenes were approved by the director on a prior CLIP subject check alone; no direct visual proof of an invisible mechanism exists.

## Required end-to-end architecture

1. **Science screen (unchanged)**: approve truthful factual narration first. No unsupported mechanisms or numbers.
2. **Scene intents**: create a visual contract for every spoken segment containing (a) physical subject and visible action, (b) exact search query, (c) permitted illustration vs literal event, (d) forbidden misleading subjects and compositions, (e) scene-specific reference relevance. A spectator's act of looking is *not* automatically the subject of a physics lesson.
3. **Multi-source discovery**: use available license-eligible stock providers, multiple precise queries and synonyms, bounded retry budgets, caching and collision-free media IDs. Do not loosen licensing or invent the visual.
4. **Candidate-level preflight**: retain provider metadata, native portrait resolution, actual video duration, motion, frame-level CLIP and unique content hash checks. Hard negatives must include plausible lookalikes (gray sky, sunset silhouette, portraits), not only unrelated objects.
5. **Rank across eligible candidates**, not first-eligible selection. Compare same-scene candidates after vertical crop. Download/infer only on top-K candidates per provider to respect GitHub Actions limits. A higher semantic score is still *not factual proof*.
6. **Visual understanding**: only if CLIP cannot decide, optionally run a locally hosted/open-weight small frame/video caption model on ~3 cropped frames of the best candidates and compare visible objects/actions with the spoken clause. No paid API; benchmark CPU wall-clock, RAM, download and licensing first. Caption models can hallucinate: require multi-frame evidence.
7. **Scene repair**: when a required image is unavailable, change the *visual plan* first. If this would be misleading, rewrite the science-screened sentence using the same independent sources, rather than filling with a random unrelated clip. Bound retries; leave the run failed if still no acceptable material.
8. **Rendered-video audit**: sample the actual finished 9:16 MP4 at scene boundaries/midpoints and compare against the approved scene intents. Verify audio, captions, timing, black frames, subject visibility and visual contradictions.
9. **Publishability gate**: technical success and visual alignment are **separate**. Output MP4 exists != all scene claims are visually supported. Maintain detailed `visual_alignment_report.json` with scene IDs, candidate scores, reject explanations, source license and final acceptance.
10. **Reproducibility and zero-budget**: cache CLIP/caption model downloads; do not rely on paid inference, use API quota-aware searches. Avoid a 10-video concurrency surge; add long-form and German only after short-form visual alignment is proven on real materials.

## Immediate changes implemented in PR #61
- Rewrite a specific sky-science "we look upward" reaction-shot visual plan to the actual sky while leaving narration untouched.
- Add relevant *hard negatives* for natural subjects (e.g. people walking at sunset; overcast sky versus blue sky); require positive margins across more than one sampled frame.
- Add targeted offline regressions for observational subject anchoring and hard-negative rejection.

## Acceptance tests for the full root fix
- Existing "Why Is the Sky Blue?" proof: scene 4 cannot use a portrait of a face; clear-blue-sky scenes cannot pass a clip dominated by a gray or sunset sky; sunbeams cannot be replaced by walking people.
- Composite actions (lava meets ocean; lava meets ice) require actual co-occurring visual evidence, not merely general-topic clips.
- Blindness to footage: avoid claiming an invisible scientific mechanism is filmed literally.
- Validate EN and DE, at least 5 distinct science/nature topics (including scarce footage cases), a 10-topic batch and a real 10-minute video.
- Real video QA and human review should agree on **each scene**, not just on the output's ability to play. Track false-positive and false-negative footage decisions; calibrate thresholds from these labeled examples.
- If video content does not exist in accessible licensed stock, report unavailability clearly. No solution guarantees a literal stock clip for every conceivable event.
