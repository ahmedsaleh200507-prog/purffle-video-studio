"""Patch upstream Groq HTTP compatibility with the supported Groq Python SDK."""
import os

try:
    from purffle_shorts.llm import OpenAICompatible
    from groq import Groq

    _original = OpenAICompatible.complete

    def _complete(self, system, user, *, schema=None, temperature=0.9, max_tokens=4000):
        if self.name != "groq":
            return _original(self, system, user, schema=schema, temperature=temperature, max_tokens=max_tokens)
        client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=65, max_retries=1)
        reasoning = "gpt-oss" in self.model
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_completion_tokens": min(max_tokens, 4096),
        }
        if reasoning:
            kwargs["reasoning_effort"] = "low"
        else:
            kwargs["temperature"] = temperature
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            # Some models do not accept response_format; retry without it once.
            if "response_format" not in str(exc).lower() or "response_format" not in kwargs:
                raise
            kwargs.pop("response_format", None)
            response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Groq returned empty content")
        return content

    OpenAICompatible.complete = _complete
except Exception as exc:
    print("Groq SDK patch initialization failed:", type(exc).__name__, str(exc)[:250], flush=True)
