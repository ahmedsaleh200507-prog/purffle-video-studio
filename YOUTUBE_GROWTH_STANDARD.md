# Purffle — YouTube Growth and Monetization Production Standard

This is the permanent production contract for the existing "Purffle V2 - 1 to 10 Videos" workflow. Optimize original, trustworthy educational Shorts for real audience interest and sustainable earning potential. **Never guarantee views, revenue or YPP approval.**

## Mandatory topic-adaptive four-phase Shorts — NOT fixed to 30 seconds

The producer estimates an **editorial target** from the topic, real verified
footage and available facts. A simple subject can naturally finish in roughly
15–25 seconds; an explanation with more useful facts may use 30–45 seconds or
longer when supported by verified scenes. The actual MP4 duration is determined
by real narration, never a mandatory target.

| Phase | Relative goal | Editorial requirement |
|---|---|---|
| HOOK | **First 1–2 seconds, always** | Immediately show the strongest verified real action with a short, truthful, concrete spoken line. NO giant title or idle intro |
| CURIOSITY | Immediately after hook | Give a meaningful early fact and reason to continue, never artificial suspense |
| DEVELOPMENT | Main body, as long as necessary | Every verified shot adds genuinely new explanatory value; no generic filler or repeated facts |
| PAYOFF | Last part of each video | Answer the question clearly and finish with related original explanation, no CTA or fake cliffhanger |

The old 0–2 / 2–8 / 8–22 / 22–30 example is **only a reference for a
30-second video**, not a deadline. The phases adjust to the real final length.
This is a story structure, not precisely four camera clips or cuts. Never loop
or stretch footage and narration to fill time. **Quality of the first seconds
is prioritized over quantity of video minutes or number of uploads.**

## Nonnegotiable technical standards

- Real moving camera footage from a licensed source. Independent source-resolution, clip-motion, visual match, first-seconds impact and uniqueness checks all stay enabled.
- Portrait 720x1280, 30 FPS, audible narration, synchronized yellow/white word captions; no giant upper title and no PurffleStudios watermark or background music.
- English uses the approved private male reference voice, with real ASR and speaker-identity checks. German uses approved Thorsten. Never substitute a different English speaker.
- Scripts must be genuinely informative and different for each topic, scientifically verified and paired with images honestly representing the subject. Never manufacture measurements, studies or sensational claims.
- Prefer quality and authenticity to high-volume interchangeable content. A single failure must not be labeled a successful video.

## Measure actual YouTube performance

Compare the same **YouTube Studio** measures for every published Short: (a) Stayed to watch / swiped away, (b) average percentage viewed and retention graph, (c) engaged views and subscriber gain. Include the topic, actual hook and length. These are observations **after publishing**, not automatically predictable from code. A producer report must not invent YouTube analytics.

## Monetization and official 2027 rules

YouTube announced changes starting **February 1, 2027**: new applicants for full ads and Premium sharing need **1,000 subscribers** and either **8,000 qualified watch hours in 365 days** or **20 million qualified Shorts views in 90 days**. Earning from the Shorts Creator Pool in a given month additionally requires maintaining **10 million qualified Shorts views over the previous 90 days**. Other early fan-funding thresholds apply. Every channel undergoes independent monetization policy review: mass-produced, generic, reused content can be ineligible even with licensed footage.

Sources: 
- https://support.google.com/youtube/answer/12843009
- https://support.google.com/youtube/answer/1311392
- https://support.google.com/youtube/answer/13429240

## Implementation map

- scripts/opening_impact.py: screen the first real seconds and rank verified candidate footage.
- scripts/retention_storyboard.py: determine adaptive duration and write/audit the four-phase narrative before voice.
- scripts/media_first.py: select and preserve actual verified footage and advance unique facts.
- scripts/studio_runtime.py: original science/voice/captions with topic-adaptive editorial prompt.
- scripts/render_job.py: script review, independent science screen, finished MP4 checks.
- scripts/batch.py: save retention-report.json in each video artifact.
- tests/test_four_phase_short.py: enforce the production contract.

**Goal:** make videos viewers genuinely want to finish, then use real retention data to improve. This system cannot promise a viral video or income.
