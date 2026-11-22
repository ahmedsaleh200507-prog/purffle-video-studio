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
   button is needed. Keep `GROQ_API_KEY` if you want it as the first model.

## Routing behavior

**Shorts:** Gemini 3.1 Flash-Lite is the primary whenever its key is
present. Groq GPT-OSS-20B is automatically available as a secondary
provider if both keys exist. If only Groq has a key, it is used directly. The English approved-reference and German
Thorsten voices are still mandatory; video source, science and CLIP guards
are unchanged.

**Long video:** Groq writes the 14-section JSON script as usual. On Groq
429 or the specific generated-invalid-JSON error, Gemini receives the
SAME JSON requirements and the accepted response still passes the original
local length and chapter validators. If Groq is unavailable/missing,
Gemini is used directly. To prioritize Gemini when both secrets are present,
open GitHub **Settings → Secrets and variables → Actions → Variables** and
create a repository variable named `PURFFLE_LONG_LLM_PRIMARY` with value
`gemini`. The long-batch workflow reads this variable. This setting is optional.

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

**Testing status:** Automated regression tests check that the key is never
written to reports or artifacts and that API failover does not bypass any
local validators. An actual Gemini inference run is only possible once the
repository's own `GEMINI_API_KEY` is present. Do not claim production
success before a real MP4 is rendered and inspected.
