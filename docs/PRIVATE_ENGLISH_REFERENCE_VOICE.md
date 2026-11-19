# One permanent English narrator — private reference only

**Status:** The English voice route is implemented, but it cannot render in
GitHub Actions until the repository has the required private reference Secret.
The real CPU model, speaker similarity, ASR transcript and caption timings must
pass a live workflow run. Offline CI success is not voice-clone validation.

The user-approved original 10-second 16kHz mono PCM WAV is identified by
SHA256 `6cc53c46241503f7c6a813ecf98f726eec38bfae33177d624b4ac9190fc41146`.

We use a **private, 24kbps Opus representation** of that specific recording,
SHA256 `af686af58b15ff2842829d42217bc852d834acef5720d813b25136527b90bcf0`.
This tiny copy is **not in git**, which is public. The voice recording must
never be committed, uploaded to Actions artifacts, sent to external AI voice
services, or printed to logs.

## One-time private secret setup

1. Open
   https://github.com/ahmedsaleh200507-prog/purffle-video-studio/settings/secrets/actions
2. Click **New repository secret**.
3. Name: `PURFFLE_REFERENCE_OPUS_B64`
4. Value: copy the complete one-line value from the private
   `PURFFLE_REFERENCE_OPUS_B64.txt` file supplied to the repository owner
   in ChatGPT. This is the 10-second approved private Opus clip encoded
   with standard base64, about 39 KB text, below the GitHub Actions 48 KB
   secret limit.
5. Save the secret. **Never paste its value into a GitHub issue, workflow
   input, code file, comment or public chat.**

This GitHub integration cannot create or edit the encrypted repository
Secret, so the owner must perform this one-time action. Setting it does NOT
prove cloned speech is identical; the live smoke must pass.

## What happens automatically on English runs

- Preflight verifies the secret's exact SHA256 before installing production
  tools, aborting with `reference_voice_not_ready` otherwise.
- The 10s Opus is decoded locally in a private runner temp folder and wiped
  after synthesizing. The model never uploads this clip to an outside API.
- Isolated local CPU `chatterbox-tts==0.1.7`, Nano
  `ResembleAI/chatterbox-nano`, uses ONLY this reference clip for English
  speech. English Piper Joe, LJSpeech and Edge routes were removed/disabled.
  The German narrator remains `de_DE-thorsten-medium`.
- The actual output WAV is transcribed using local faster-whisper base.en with
  word timestamps; each spoken token must exactly match requested narration
  and be timed against the actual audio (not estimated word-duration guesses).
- Resemblyzer compares the same reference and generated voice embeddings; a
  cosine below 0.70 blocks the video. This is an automated similarity screen,
  **not a scientific guarantee of identical identity**.
- The final MP4 validator demands metadata `reference:approved-reference-male-...`,
  a complete voice report, correct reference fingerprint and speaker/word
  gates. **No fallback narrator** if any step fails.
- On GitHub-hosted CPU runners, model download/inference can be slow. This
  does not incur a paid TTS service fee, but Actions runner usage and provider
  quotas are still subject to the user's GitHub plan.

Important: Only enable English video production after a live smoke has
actually proved the expected voice and caption output. An automated cosine
threshold is not the same as the owner's listening approval. If the voice
does not sound sufficiently similar, do not publish it.

Official model documentation: https://github.com/resemble-ai/chatterbox
(MIT license, Nano English CPU zero-shot voice cloning).
