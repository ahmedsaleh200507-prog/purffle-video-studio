# Text and vision specialist rollout (experimental)

No changes to live narration, stock selection, CLIP/DINO, rendering, voice or publication. The pilot uses exact model IDs with no model substitution and saves every response and error. Existing free-account Google and Groq credentials are reused; account billing status cannot be inferred by API key. Do not enable paid plans, search grounding or chargeable fallback. New providers are disabled until the owner confirms a free account: add OPENROUTER_API_KEY or CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID in repository Actions secrets; set the matching PURFFLE_OPENROUTER_FREE_CONFIRMED or PURFFLE_CLOUDFLARE_FREE_CONFIRMED variable to 1 only after verifying no paid billing. Never share a key in chat. OpenRouter uses explicit :free model IDs and zero price ceilings.

## Separate evaluation
- Phase 1: actual access and two initial bilingual text samples from shared sources. Two known still image fixtures with reversed positive/negative questions for vision. This is a smoke test, not a representative ranking.
- Phase 2: shortlist text writers on at least five topics in both languages using identical sources, blind human reading plus independent source-aware review. No self-judging or treating API failures as quality failures. Track output coverage, factual errors, exact-answer relevance, native language and sentence completeness. Weighted editorial scoring: hook 30, continuation 25, interesting facts 20, spoken flow 15, ending 10.
- Phase 2 vision: fixed licensed real footage and hard negatives, multiple sampled frames, independently labeled subjects/actions, exact model ID, false acceptances, false rejections, abstentions, latency, quotas. Still image results cannot prove actions, identity, temporal continuity or licensing. Existing visual gates remain authoritative. Evaluate local Florence-2/Qwen3-VL and CLIP/DINO alongside cloud alternatives. No replacing them based on two images.
- Phase 3: select specialists separately (writer per language, source reviewer, footage relevance reviewer). Keep API quota/backoff and stage checkpointing as separate engineering work. No automatic promotion. Full Shorts test and manual review first; long documentaries later.

Official references:
- https://ai.google.dev/gemini-api/docs/pricing
- https://console.groq.com/docs/model/qwen/qwen3.8-27b
- https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/
- https://openrouter.ai/collections/free-models

## Additional writer candidates (2026-11-28)
Gemini 4 Hydrogen (already in the older production router, now an isolated exact-ID writer candidate), ERNIE-5.5-Flash-Preview and Gemma 4 26B A4B via explicit OpenRouter free variants. Gemini 3.8 Flash remains in the first audition. Arena creative-writing preferences dated 2026-11-22 place Hydrogen (xHigh) at rank 8 and Flash (High) at rank 10; those configurations are not proven equivalent to our API settings or a documentary-writing benchmark. Google lists standard free-tier input and output for both; verify the actual account. No deprecated Gemini 3.7 alias and no paid Claude/DeepSeek variants added. OpenRouter candidates remain disabled until a free account/key is configured.

The additional workflow is manual-only on purpose: finish the current text/vision pilot first, then run the small additional writer audition before spending quota on a full bilingual comparison. No competing automatic workflow, no automatic production promotion.

References:
- https://arena.ai/leaderboard/chat/text/creative-writing
- https://arena.ai/leaderboard/chat/text/german
- https://openrouter.ai/baidu/ernie-5.5-flash-preview:free
- https://openrouter.ai/google/gemma-4-26b-a4b-it:free

## Follow-up after the first completed pilot
The initial run returned seven nonempty text responses, including a Gemma response containing non-narration notes and out-of-range outputs. This is not seven publishable scripts. Reject wrappers and out-of-range narration before saving candidate text. The follow-up retries the two incomplete Google auditions and adds Hydrogen; optional OpenRouter candidates remain inactive without credentials and free-tier confirmation. The initial pilot has finished, so the follow-up is triggered by its dedicated workflow change. Neither text nor visual results select a production winner.
