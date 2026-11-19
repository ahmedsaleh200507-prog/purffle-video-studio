# Free Nature Stock — automatic, no-scraping stock video provider

## Why a finite catalog instead of a website crawler?

Official site: https://freenaturestock.com/videos/
License: https://freenaturestock.com/license/ (CC0; commercially reusable)
Terms: https://freenaturestock.com/terms/ (Section 9 explicitly prohibits
spidering, crawling, and scraping)

**We must not crawl, scrape, reverse-engineer an API, or bulk index this site.**

The video provider `freenaturestock-video` instead uses the small
`data/freenaturestock_video_catalog.json` catalog with **12 individually
reviewed links to the site's explicit official "Free Video Download" buttons**.
No requests to the site's HTML, sitemap, RSS or search pages are made from
GitHub Actions. The approved asset URLs use its own CDN at
`cdn.freenaturestock.com/videos/freenaturestock-*.mp4`.

### Zero-click usage

The existing GitHub Actions production workflows place
`freenaturestock-video` first in `VISUAL_SOURCES`.
For each requested scene the provider:

1. Looks up the stock query in the checked-in finite manifest, matching
   concrete title tokens. It does not silently supply unrelated scenery.
2. Returns only official HTTPS CDN MP4 links, rejecting any host spoofing,
   paths outside the approved `/videos/` namespace, missing/invalid
   licenses and unsuitable dimensions.
3. Uses the **existing** `StrictVisuals.for_scene` validation pipeline:
   license checking, metadata grounding, download of the MP4 through the
   existing SSRF-safe limited downloader, independent actual FFprobe and
   motion/CLIP frame screening, native vertical crop quality, deduplication,
   narrator timing and final MP4 verification.
4. Falls through to Pixabay/other enabled sources if no pre-approved
   relevant title matches or if the independent footage quality check rejects
   the file. A match by title alone is NOT evidence that a video was usable.

No API key is needed for the finite catalog. Real CDN reachability or full
MP4 downloads must be confirmed on an Actions runner. The curated set is
**not a complete mirror of the site** and does not automatically discover
new uploads. New URLs can only be added following independent, authorized
review of the original download button/link and the site's current terms.
Do not add HTML/RSS/JSON page scrapers or invent CDN filenames.

### Licensing and publication

The CC0 license applies to the video clips, not necessarily to recognizable
people/trademarks shown within them. Original source pages are retained in
the credit/provenance report. A stock video of a starry sky is **not footage
of the aurora**; local scene matching must reject it for an aurora-specific
scene. The English narrator remains locked to the user's approved private
reference speaker, which still cannot generate verified new English speech;
**adding a stock source does not make blocked English videos producible**.

### Limitations

- Initial catalog: 12 sources across ocean, clouds, stars, forest, river,
  leaves and campfire; no genuine aurora or lightning footage identified.
- Large 4K files may take time to download. Downloads respect the existing
  350MB/file, total 180s, native-resolution and license checks.
- Site terms may change; reviewed links may stop working.
- Do not claim successful download or a finished video on the basis of a
  passing unit test alone.

Catalog source pages and link names were checked against official site
on 2026-11-19.
