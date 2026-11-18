# PR #18 — Private reference voice audition (NOT production voice)

The public repository deliberately contains **no reference audio, transcript
or speaker embedding**. Uploading a user-provided voice to a public source
repository, even as an apparently innocent clip, would expose the speaker.

The existing **production** voice remains pinned Piper Joe (English) and Piper
Thorsten (German). Their stable identity is not a claim that they are the
speaker in the user's MP4. New scripts/videos continue with the production
voice until an explicit change is tested and authorized.

## Optional evaluation

This experimental CLI uses the official Apache-2.0
`Qwen/Qwen3-TTS-12Hz-0.6B-Base` checkpoint at
`5d83992436eae1d760afd27aff78a71d676296fc`.
It can clone speaker characteristics from a private 6–15 second mono PCM
16kHz/24kHz WAV and supports English and German. Neural cloning is *never*
provably identical by model selection alone. The WAV must be an authorized
speaker recording with a clean enough passage and known transcript for the
best attempt. Ordinary YouTube/third-party rights still apply.

1. Create or select a 6–15 second speech-only WAV *outside the public repo*.
2. For an isolated, manually reviewed audition environment, install
   `qwen-tts`, `soundfile`, `torch` and `numpy` per the upstream model
   docs. Test model CPU RAM and generation time before integrating with
   GitHub Actions; no such production test has been completed.
3. Compute `sha256sum /private/reference.wav`.
4. Run (not part of regular batch):

```sh
python scripts/reference_voice_audition.py \
    --reference /private/reference.wav \
    --expected-sha256 YOUR_64_CHARACTER_REFERENCE_HASH \
    --ref-transcript 'Exact words spoken in the private reference sample' \
    --text 'Why do onions make your eyes water?' \
    --language en \
    --output /private/audition.wav
```

A less faithful *audition only* can use `--x-vector-only` instead of a
transcript. The script produces a WAV plus a JSON report with status
`audition_only_unverified_similarity`, and **never** claims identity matching.

## Mandatory before production

- Evaluate listening comparison with the reference speaker and confirm
  consent/right to voice cloning.
- Confirm model CPU/RAM runtime and free usage limits on the chosen runner.
- Confirm speech/no background music and actual voice similarity.
- Implement and measure word-level subtitle alignment for the newly generated
  voice (Piper's native phoneme sample alignments do NOT automatically apply).
- Confirm the generated WAV stream, exact profile hash and identity are
  stable enough across at least English/German tests.
- Enforce strict **fail-closed** behavior, no silent switch to Joe or female.
- Provide a private way to supply the reference on each isolated Actions run,
  without committing the source to the public repo.

This PR is specifically a **non-activating experiment**. Neither CI unit
tests nor the existence of a model demonstrates perceptual voice fidelity.
Sources:
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base
- https://github.com/QwenLM/Qwen3-TTS
