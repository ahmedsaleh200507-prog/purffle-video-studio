"""Paid narration is disabled by the project free-only policy."""

def write_narration(*args, **kwargs):
    raise RuntimeError("Paid narration is disabled; use the existing free-tier writer.")
