# 10 independent long documentaries (English / German)

## iPhone / GitHub Actions usage

Open **Actions** → **02 - Long Video Maker (1-10 videos, EN/DE, 16:9)** → **Run workflow** on the `main` branch.

Enter **one topic per field** with an explicit language prefix:

- `video_1: en|Why do octopuses have three hearts?`
- `video_2: de|Warum ist der Himmel blau?`
- `video_3: en|What happens deep inside the ocean?`
- Fill up to `video_10`, or leave remaining fields blank.

The first field is required. Do not paste ten topics into one field. The workflow is separate from the existing **01 - Shorts Video Maker** workflow.

Each non-empty slot starts its own 14-chapter long-documentary job with:
- English: the previously approved private male reference narrator (requires the existing GitHub Secret `PURFFLE_REFERENCE_OPUS_B64`).
- German: the locked, audited CC0 **de_DE-thorsten-medium** Piper narrator, without an English/female fallback.
- Script and chapter-specific English footage search generated for the actual topic.
- Real licensed stock footage screened by existing quality, local CLIP and source metadata filters.
- 1920×1080 H.264 MP4, 9–11 min measured duration, AAC voice normalized to −17 LUFS.
- **No embedded subtitles**; an optional standalone `captions.srt` is provided.

The ten jobs run **one at a time** to reduce API rate-limit errors. A failed slot does not cancel another slot (`fail-fast: false`). Each selected slot has an individual artifact named **`long-video-<number>-en`** or **`long-video-<number>-de`**; artifacts include a final MP4 only on successful verification. A failure uploads the available report and diagnostics, rather than a fake video. Empty slots are skipped before expensive dependency installation.

## Constraints and costs

- Topic length: 8–180 characters; one topic per slot.
- Model script output, narrator availability and **real footage availability** are dependencies. An obscure topic may fail if no verifiable HD stock exists; automated publication is intentionally disabled.
- German Piper's natural speaking rate may not achieve 9–11 minutes with every generated narration. The renderer measures the actual audio and fails rather than silently adding dead air. Language-specific timing is **not yet guaranteed on real German 10-minute output**.
- High-volume long video rendering consumes substantial **GitHub Actions minutes, storage and Groq/Pixabay/Pexels quotas**. Check your own GitHub account's billing and Actions usage before requesting ten simultaneous projects.
- Review factual accuracy, narration and clip-topic relevance before YouTube publication. Stock footage cannot prove scientific or historic assertions.
- `long-video-output` from each job is not automatically uploaded to YouTube. Artifact retention in this workflow is **7 days**.

## Scope

This batch workflow uses only `scripts/long_batch_slot.py`, `scripts/long_generic.py` and the isolated `scripts/long_video.py` long-documentary path. The 9:16 Shorts `scripts/batch.py`, `.github/workflows/videos.yml` and their locked narrator behavior remain unchanged.


## Workflow menu cleanup (22 November 2026)

The user-facing Actions menu has two production workflows only:

- `01 - Shorts Video Maker (9:16)` — 1–10 short vertical videos
- `02 - Long Video Maker (1-10 videos, EN/DE, 16:9)` — 1–10 long videos, independently English or German

`90 - INTERNAL | Automatic code tests` and `91 - INTERNAL | Pull request validation` are automatic safety tests, not video makers. Old test and single-topic production workflows were removed from `.github/workflows/` to eliminate confusion; recoverable copies remain in the `archive/workflows-before-cleanup-20261122` Git branch and ordinary Git history.
