"""Free-tier Groq -> Google Gemini fallback for long-form JSON narration.

The main video and the science/stock validation policy are unchanged. This
adapter only generates an untrusted JSON candidate; the existing 14-chapter,
word-count and scene/source validators still decide whether to accept it.

Uses the documented Gemini OpenAI-compatible HTTPS endpoint without
requiring an additional SDK. No provider tokens are included in diagnostics.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

GROQ_MODEL = "openai/gpt-oss-20b"
GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


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
        if response.status_code != 200:
            # Do not include HTTP body or credentials in GitHub logs.
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
        # Never attempt a provider whose API key is not configured.
        if self.prefer == "gemini" and self._gemini_key:
            return self._gemini(**kwargs)
        if self._groq is not None:
            try:
                return self._groq.chat.completions.create(**kwargs)
            except Exception as exc:
                if not self._gemini_key or not _groq_retryable(exc):
                    raise
                print("[LONG LLM] Groq generated-JSON error or limit; "
                      "switching to Gemini free text model", flush=True)
                return self._gemini(**kwargs)
        if self._gemini_key:
            return self._gemini(**kwargs)
        raise LongLLMUnavailable(
            "No free LLM API key. Configure GROQ_API_KEY or GEMINI_API_KEY.")


class LongLLM:
    def __init__(self, *, groq=None, gemini_key: str = "", post=None,
                 prefer: str = "groq"):
        self.chat = SimpleNamespace(completions=_Completion(
            groq=groq, gemini_key=gemini_key,
            post=post, prefer=prefer))


def get_long_client(*, groq=None, post=None, environ=None):
    """Select Groq with Gemini recovery, or Gemini alone if Groq is absent.

    Explicit PURFFLE_LONG_LLM_PRIMARY=gemini lets users conserve Groq quota,
    but only if GEMINI_API_KEY is provided. No auto-billing setup.
    """
    env = os.environ if environ is None else environ
    primary = env.get("PURFFLE_LONG_LLM_PRIMARY", "groq").strip().lower()
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
