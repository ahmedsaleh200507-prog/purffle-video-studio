# English narrator identity — reference-only policy (approved 18 November 2026)

The user **explicitly approved** the speaker in the privately supplied
10-second PCM WAV and requires **that same man for every English-language
video**. This is NOT the current Piper Joe speaker.

The approved reference recording fingerprint is
`6cc53c46241503f7c6a813ecf98f726eec38bfae33177d624b4ac9190fc41146`
(SHA-256), mono 16-bit PCM, 16kHz, 10 seconds.

## Enforced rule

All strict English productions are now **fail-closed** at three points:

1. Before downloading tools in GitHub production workflows, the reference
   voice preflight rejects a request while approved reference cloning is
   not deployed. This avoids paying for unused runner setup time.
2. In the Python render worker, the exact same preflight happens before
   real stock search and script drafting.
3. In the voice and final MP4 validation paths, the reference rule is checked
   again so no bypass silently publishes Piper Joe.

The error is `reference_voice_not_ready`, classified as
`approved_english_voice_unavailable`; this is a **failed job**, not a
successful MP4. Other voices (Piper Joe, Edge, female LJSpeech, etc.) must
**never** be substituted in the user's English production.

**Important:** This is an identity lock and does NOT yet synthesize the
reference speaker. The experimental `scripts/reference_voice_audition.py`
may generate comparison audio in a private environment using the Qwen3 Base
speaker prompt, but no **live reference clone** has been shown to match the
speaker, nor has its subtitle alignment been tested. A reference file hash
only establishes which input recording was approved. It does NOT prove the
generated voice is perceptually identical.

## Deployment blockers before re-enabling English production

- Deliver approved WAV privately to the runner (not via public GitHub
  repository or commit).
- Choose a voice cloning engine permitted for intended publication.
- Test output audibly against the reference and confirm consistent speaker
  identity on multiple separate English samples.
- Generate true aligned word timestamps for the *cloned* narration.
- Save hash of reference and output speaker provenance in each job report.
- Validate end-to-end MP4 and never allow fallback to a substitute voice.

German productions are unchanged and may use pinned Piper Thorsten.
Existing validated MP4s are not deleted. No automatic replay of the failed
five-video daily-life run is triggered by the branch change or the merge.
