# Coverr — free authentic HD/4K video API in Purffle

Official product: https://coverr.co/developers
Official current API: https://api.coverr.co/docs/videos/
Official Nov 4, 2026 license: https://coverr.co/license

Coverr provides authentic MP4 stock clips at HD/4K and a free Demo
tier: **50 API requests/hour, no credit card required**. The November
2026 license explicitly allows commercial use on all API tiers, with
extra **attribution** for free API apps and mandatory
`PATCH /videos/:id/stats/downloads` on actual downloads.

## Ready-to-use source

The GitHub Actions workflows now include `coverr-video` immediately after
the finite Free Nature Stock catalog and before Pixabay.
`COVERR_API_KEY` is read **only from GitHub Actions Secrets**, not committed.
To get one: https://coverr.co/developers → Profile → API / Create app,
then save as the `COVERR_API_KEY` GitHub Repository Secret.

For each filmable scene, the provider searches the official
`https://api.coverr.co/videos` endpoint with `urls=true` and
`filter=is_ai_generated:false`; results are checked independently:

- **Only real video:** require `is_ai_generated is False` exactly.
  Records without an explicit AI-origin boolean are rejected.
- **Only free, licensed content:** exclude sponsored/partner Shutterstock,
  iStock etc., premium or watermarked clips.
- **Only full MP4:** use signed `urls.mp4`, never preview/still-image URLs.
- **No unknown hosts:** allow only original signed video links on
  `storage.coverr.co` or `cdn.coverr.co` with HTTPS `/videos/` paths.
- **Only correctly matched moving clips:** apply original metadata grounding,
  FFprobe, real motion, image-content frame matching, native 720p 9:16
  crop, scene length, valid license and duplicate SHA256.
- **Free API attribution:** add `Video by [creator] on Coverr`, link to
  their Coverr profile when available, and cite coverr.co and source
  page in the finished video's source credits.
- **Download reporting:** send authenticated PATCH for every downloaded
  Coverr clip, even before it passes final visual relevance screening.
  A denied/missing tracking call rejects the clip, not the whole Short.
- **No key/token leakage:** signed `urls.mp4` can contain an API-key-linked
  JWT. Raw Coverr API responses are never persisted in GitHub cache. Once
  the file is downloaded and verified, the in-memory MediaItem.url is
  replaced by its safe public Coverr source page before metadata/artifact
  reports are written. Never log the API key or signed download URL.
- **Quota bounds:** maximum **5 Coverr requests per video job**, including
  searches and download PATCH calls, default configurable via
  `PURFFLE_COVERR_MAX_CALLS`. When exhausted the provider is bypassed
  and the existing stock providers continue.

## Limitations

- Free Demo tier is **rate limited**, not unlimited commercial production
  access. Coverr advertises a paid Pro/Ultimate plan for higher volume.
- The source's status cannot be called "working" from unit tests alone.
  An authenticated GitHub Actions test must show a real API search, real
  MP4 download, valid FFprobe/motion quality and successful PATCH.
- Authentic footage is original camera material. We do **not** enable
  Coverr's AI generation endpoints or use Coverr for training/testing
  AI models or building a competing stock-video service.
- Film clips may still be rejected if their content does not directly
  match the requested Shorts topic or they cannot deliver a true 720p
  vertical crop. Other sources will be tried.
- The unrelated English private narrator is still required for English
  Shorts; adding Coverr does not solve voice similarity if pending.

License and pricing checked 2026-11-19:
https://coverr.co/license
https://coverr.co/developers
https://api.coverr.co/docs/videos/
