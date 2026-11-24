"""Free-tier Groq -> Google Gemini fallback for long-form JSON narration.

The main video and the science/stock validation policy are unchanged. This
adapter only generates an untrusted JSON candidate; the existing 14-chapter,
word-count and scene/source validators still decide whether to accept it.

Uses the documented Gemini OpenAI-compatible HTTPS endpoint without
requiring an additional SDK. No provider tokens are included in diagnostics.
"""
from __future__ import annotations

import os
import re
import time
from types import SimpleNamespace
from typing import Any

GROQ_MODEL = "openai/gpt-oss-20b"
GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def _minute_retry_delay(error):
    """Recover a rolling per-minute limit without spending money or disabling
    the provider for the entire documentary. Daily quota remains a hard limit."""
    if getattr(error, "status_code", None) != 429:
        return None
    message = str(error).lower()
    if "per day" in message or "daily" in message or "(tpd)" in message or "(rpd)" in message:
        return None
    if not any(term in message for term in ("per minute", "(tpm)", "(rpm)")):
        return None
    match = re.search(r"try again in\s+([0-9.]+)\s*s", message)
    delay = float(match.group(1)) + 3 if match else 65
    return min(70, max(5, delay))


class LongLLMUnavailable(RuntimeError):
    pass


class LongLLMResponseError(RuntimeError):
    def __init__(self, label: str, status: int):
        self.status_code = status
        super().__init__(f"{label}: HTTP {status} (check model quotas and key)")


def _groq_retryable(error: Exception) -> bool:
    """Only Groq generated invalid JSON and rate exhaustion are recoverable."""
    if getattr(error, "status_code", None) == 429:
        return True
    from long_script import is_groq_json_validation_error
    return is_groq_json_validation_error(error)


class _Completion:
    def __init__(self, *, groq=None, gemini_key: str = "", post=None,
                 prefer: str = "groq"):
        self._groq = groq
        self._gemini_key = gemini_key
        self._post = post
        self.prefer = prefer
        # One video's failed provider must not consume every later chapter's
        # minute/day quota through repeated, predictable HTTP 429 calls.
        self._quota_exhausted = set()

    def _gemini(self, **kwargs):
        import requests
        sender = self._post or requests.post
        payload: dict[str, Any] = dict(kwargs)
        payload["model"] = GEMINI_MODEL
        # Google Gemini's OpenAI-compatible endpoint accepts the JSON output
        # contract. The existing local validation remains authoritative even
        # if the model returns valid JSON that does not match chapter counts.
        fmt = payload.get("response_format") or {}
        if fmt.get("type") == "json_schema":
            schema = dict(fmt["json_schema"])
            schema.pop("strict", None)  # Compatibility: local checks stay strict.
            payload["response_format"] = {"type": "json_schema",
                                          "json_schema": schema}
        try:
            response = sender(
                GEMINI_URL,
                headers={"Authorization": f"Bearer {self._gemini_key}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=(10, 120),
            )
        except (requests.RequestException, OSError) as ex:
            raise LongLLMUnavailable(
                f"Gemini connection failed: {type(ex).__name__}") from None
        if response.status_code in (400, 422) and fmt.get("type") == "json_schema":
            # Some Gemini OpenAI-compatible model versions refuse strict
            # schema keywords. Try JSON mode ONCE and keep original local
            # 14-section/word-count validation. Never accept arbitrary prose.
            fallback = dict(payload)
            fallback["response_format"] = {"type": "json_object"}
            response = sender(
                GEMINI_URL,
                headers={"Authorization": f"Bearer {self._gemini_key}",
                         "Content-Type": "application/json"},
                json=fallback, timeout=(10, 120),
            )
        if response.status_code != 200:
            # Never log the response body, API key, or request headers.
            raise LongLLMResponseError("Gemini", response.status_code)
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty Gemini JSON")
            finish = choice.get("finish_reason") or "stop"
        except (TypeError, ValueError, IndexError, KeyError):
            raise LongLLMUnavailable("Gemini returned no usable JSON") from None
        return SimpleNamespace(choices=[
            SimpleNamespace(
                finish_reason=finish,
                message=SimpleNamespace(content=content)
            )])

    def create(self, **kwargs):
        configured = (
            ["gemini", "groq"] if self.prefer == "gemini"
            else ["groq", "gemini"]
        )
        enabled = {
            "gemini": bool(self._gemini_key),
            "groq": self._groq is not None,
        }
        available = [provider for provider in configured
                     if enabled[provider] and
                     provider not in self._quota_exhausted]
        if not available:
            raise LongLLMUnavailable(
                "No free LLM provider available. Check Groq/Gemini quotas.")
        for index, provider in enumerate(available):
            try:
                if provider == "gemini":
                    return self._gemini(**kwargs)
                for attempt in range(5):
                    try:
                        return self._groq.chat.completions.create(**kwargs)
                    except Exception as exc:
                        delay = _minute_retry_delay(exc)
                        if delay is None or attempt == 4:
                            raise
                        print(f"[LONG LLM] Groq minute quota; retry {attempt+1}/4 after {delay:.1f}s",
                              flush=True)
                        time.sleep(delay)
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                is_quota = status == 429
                transient = (status in (408, 500, 502, 503, 504)
                             or isinstance(exc, (LongLLMUnavailable, OSError, TimeoutError))
                             or type(exc).__name__ in ("APIConnectionError", "APITimeoutError",
                                                       "ReadTimeout", "ConnectTimeout", "ConnectionError"))
                invalid_groq_json = (
                    provider == "groq" and _groq_retryable(exc))
                if is_quota or status in (401, 403, 404):
                    self._quota_exhausted.add(provider)
                unavailable = status in (401, 403, 404)
                if not (is_quota or transient or invalid_groq_json or unavailable):
                    raise
                if index == len(available) - 1:
                    raise
                print(f"[LONG LLM] {provider} quota/transient/JSON error; "
                      f"trying {available[index+1]} with identical script contract",
                      flush=True)
        raise LongLLMUnavailable("All configured script providers unavailable")

class LongLLM:
    def __init__(self, *, groq=None, gemini_key: str = "", post=None,
                 prefer: str = "groq"):
        self.chat = SimpleNamespace(completions=_Completion(
            groq=groq, gemini_key=gemini_key,
            post=post, prefer=prefer))


def get_long_client(*, groq=None, post=None, environ=None):
    """Prefer Gemini on its 500 RPD free tier; recover through Groq.

    PURFFLE_LONG_LLM_PRIMARY=groq remains available as an opt-out. Both
    providers fail closed on malformed content after the existing validators.
    """
    env = os.environ if environ is None else environ
    primary = env.get("PURFFLE_LONG_LLM_PRIMARY", "gemini").strip().lower()
    if primary not in ("groq", "gemini"):
        raise ValueError("PURFFLE_LONG_LLM_PRIMARY must be groq or gemini")
    gemini_key = env.get("GEMINI_API_KEY", "").strip()
    groq_key = env.get("GROQ_API_KEY", "").strip()
    if not groq and groq_key:
        from groq import Groq
        groq = Groq(api_key=groq_key, timeout=120)
    if not groq and not gemini_key:
        raise LongLLMUnavailable(
            "No long-video LLM key. Add GROQ_API_KEY or GEMINI_API_KEY as GitHub Secrets.")
    return LongLLM(groq=groq, gemini_key=gemini_key, post=post, prefer=primary)
