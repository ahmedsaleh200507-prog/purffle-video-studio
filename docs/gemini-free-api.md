# Free Gemini API fallback for Purffle

Purffle accepts **Google Gemini 3.1 Flash-Lite** for TEXT generation only in
both user-facing Actions workflows:
- **01 - Shorts Video Maker (9:16)** (one-to-ten videos)
- **02 - Long Video Maker (1-10 videos, EN/DE, 16:9)** (one-to-ten documentaries)

## Configure from iPhone

1. Visit https://aistudio.google.com/api-keys and select a **Free-tier**
   Google AI Studio project. Create an API key.
2. In your GitHub repository, open **Settings → Secrets and variables →
   Actions → New repository secret**.
3. Name the secret **`GEMINI_API_KEY`**. Paste the entire API key as the
   secret **Value**, then save it. **Do not paste the key into chat, workflow
   inputs, files, logs, or a Git commit.**
4. Use existing **01** or **02** from the Actions tab; no separate workflow
   button is needed. Keep `GROQ_API_KEY` as an automatic backup.

## Routing behavior

**Shorts:** Gemini 3.1 Flash-Lite is the primary whenever its key is
present. Groq GPT-OSS-20B is automatically available as a secondary
provider if both keys exist. If only Groq has a key, it is used directly. The English approved-reference and German
Thorsten voices are still mandatory; video source, science and CLIP guards
are unchanged.

**Long video:** Gemini is the primary by default when its API key is
configured. If Gemini reaches its per-minute/day quota (HTTP 429), the
system automatically uses the existing Groq GPT-OSS model for the SAME
request and does not keep hammering an exhausted provider during that
job. A generated-JSON 400, transient server 502/503/504, or Groq JSON
failure can also trigger the other provider. 401/403 invalid credentials
fail clearly; neither provider can bypass strict local chapter-count,
word-length, factual caution and visual verification.

To opt back into Groq first, set the optional GitHub repository
variable `PURFFLE_LONG_LLM_PRIMARY=groq`. Without it, Gemini is first.

This is a **script/outline API**, NOT stock footage, text-to-speech, or
unlimited video generation. Existing licensed footage availability may
still block a documentary.

## Cost and privacy

Google's Gemini API **Free tier** currently lists input and output tokens
as free for `gemini-3.1-flash-lite`; see:
- https://aistudio.google.com/docs/pricing
- https://aistudio.google.com/docs/rate-limits

Daily limits are **per project/model** and vary. They can reject a batch
with 429, just like Groq. We do not invent a fixed per-day video count.
Google discloses that Free-tier content may be used to improve its products.
Before starting ten videos, keep the project on the **Free** tier without
linked billing if you want to prevent paid usage.

**Testing status:** The GitHub real API test #45040106903 confirmed the
user's `GEMINI_API_KEY` works, and the Gemini-only real Short #45040220668
reached media verification but did not complete its MP4 (2/3 required
clips). Do not claim a fully verified Gemini video until its MP4 passes
the exact existing checks. Never expose the key or any source secret.

## Real footage is the remaining bottleneck

The last Gemini-only Short selected two of three strict 720p real-motion shots.
Pexels API was **not configured on that run**. As of **22 November
2026**, Pexels officially **paused new API key issuance**. Do not create
fake keys, scrape its website, bypass access controls, or treat Pexels as
a mandatory video dependency. Official source:
https://www.pexels.com/api/

The long-video source finder now includes **Pixabay** (existing API key),
**Wikimedia Commons** and **NASA** (public catalogs), existing
**Coverr** (only its explicitly real licensed free media, if key configured),
and **Internet Archive** (only rights-screened CC0/public-domain sources).
Every video must still pass the original metadata, 720p-native and local
CLIP frame checks. A source is not accepted simply because an API returns it.
Pexels remains optional for previously issued keys.

Long-film stock selection now prefers verified native 1080p media versions
rather than oversized 4K downloads when both are offered. It may accept
**illustrative_subject_only** clips if their actual filmed subject is verified
in **both** provider metadata and the original independent CLIP frame check;
those are labeled honestly in credits as *context*, not literal footage of an
event or invisible scientific mechanism. No synthetic or static filler is used.
