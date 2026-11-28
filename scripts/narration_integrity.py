"""Conservative offline checks; semantic completeness remains a reviewer task."""
import re

def validate_text(text, language):
    from langdetect import DetectorFactory, detect_langs, LangDetectException
    if language not in ("en","de"):
        raise ValueError("unsupported narration language")
    if not isinstance(text,str) or not re.search(r"[.!?][\"'”’»)]*$",text.strip()):
        raise RuntimeError("editorial_narration_integrity: unfinished final sentence")
    if re.search(r"\b(?:and|or|the|a|an|of|to|with|because|und|oder|der|die|das|ein|eine|mit|weil)\s*[.!?][\"'”’»)]*$",text.strip(),re.I):
        raise RuntimeError("editorial_narration_integrity: dangling final word")
    DetectorFactory.seed=0
    try:
        guesses=detect_langs(text)
    except LangDetectException as exc:
        raise RuntimeError("editorial_narration_integrity: unidentifiable language") from exc
    if guesses[0].lang!=language and guesses[0].prob>=.85:
        raise RuntimeError("editorial_narration_integrity: wrong language "+guesses[0].lang)
    return {"detected_language":guesses[0].lang,"confidence":round(guesses[0].prob,4)}
