# Purffle — YouTube Growth and Monetization Production Standard

This is the permanent production contract for the existing "Purffle V2 - 1 to 10 Videos" workflow. Optimize original, trustworthy educational Shorts for real audience interest and sustainable earning potential. **Never guarantee views, revenue or YPP approval.**

## Mandatory four-phase story (approximately 30 seconds)

| Phase | Target | Editorial requirement |
|---|---:|---|
| HOOK | 0–2s | First verified real shot is immediately compelling; strong truthful first spoken phrase; no title card or generic intro |
| CURIOSITY | 2–8s | Give a meaningful early fact that invites deeper understanding; don't delay all substance |
| DEVELOPMENT | 8–22s | New topic-specific evidence, relevant real footage and a different useful detail in each scene |
| PAYOFF | 22–30s | Clear original scientific answer and satisfying visual finish; no generic subscribe/comment CTA |

This is a storytelling framework, not exactly four camera clips or guaranteed four timecoded cuts. Adapt to the final duration, without looping, padding or inventing facts.

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
- scripts/retention_storyboard.py: write/audit the four-phase narrative before voice.
- scripts/media_first.py: select and preserve actual verified footage and advance unique facts.
- scripts/studio_runtime.py: original science/voice/captions and 30-second editorial prompt.
- scripts/render_job.py: script review, independent science screen, finished MP4 checks.
- scripts/batch.py: save retention-report.json in each video artifact.
- tests/test_four_phase_short.py: enforce the production contract.

**Goal:** make videos viewers genuinely want to finish, then use real retention data to improve. This system cannot promise a viral video or income.
