"""Validation and value rules shared by the bridge, repository, and coaches."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlparse

from .errors import ValidationError

SPEAKERS = ("customer", "rep")
SPEAKER_LABELS = {"customer": "Customer", "rep": "Representative"}
PROVIDER_MODES = ("mock", "openai_compatible")
CONFIDENCE_LEVELS = ("low", "medium", "high")
INSIGHT_TYPES = (
    "objection",
    "unanswered_question",
    "ambiguity",
    "discovery",
    "next_step",
)
INSIGHT_TYPE_LABELS = {
    "objection": "Objection",
    "unanswered_question": "Unanswered question",
    "ambiguity": "Ambiguity",
    "discovery": "Discovery",
    "next_step": "Next step",
}
PLAYBOOK_STATUSES = ("draft", "approved")

_LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ar": "Arabic",
    "ur": "Urdu",
    "hi": "Hindi",
    "bn": "Bengali",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "tr": "Turkish",
    "pl": "Polish",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "he": "Hebrew",
    "fa": "Persian",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "uk": "Ukrainian",
    "ro": "Romanian",
    "cs": "Czech",
    "el": "Greek",
}

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$")
_TIME_RE = re.compile(r"^(\d{1,3}):([0-5]\d)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_CUSTOMER_ALIASES = {
    "customer", "client", "prospect", "them", "they", "person 1", "person1",
    "p1", "speaker 1", "speaker1", "buyer", "caller", "customer 1",
}
_REP_ALIASES = {
    "rep", "sales", "sales rep", "salesperson", "representative", "me", "us",
    "you", "person 2", "person2", "p2", "speaker 2", "speaker2", "agent",
    "seller", "rep 1", "representative 1",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_local_iso() -> str:
    return date.today().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def evidence_ref(seq: int) -> str:
    return f"E-{int(seq):02d}"


def language_name(code: str) -> str:
    return _LANGUAGE_NAMES.get(code.lower(), code.upper() if code else "Unknown")


def language_pair_label(customer_language: str, rep_language: str) -> str:
    left, right = language_name(customer_language), language_name(rep_language)
    return f"{left} \u2194 {right}" if left != right else left


def normalize_language(value: Any, default: str = "en") -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if not isinstance(value, str):
        raise ValidationError("Language must be a short language code.")
    code = value.strip().lower()
    if not _LANGUAGE_RE.match(code):
        raise ValidationError(
            "Use a language code such as en, es, fr, or pt-br.",
            detail={"value": value},
        )
    return code


def normalize_time(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError("Timestamp must look like 00:42.")
    match = _TIME_RE.match(value.strip())
    if not match:
        raise ValidationError("Timestamp must look like 00:42 (minutes:seconds).")
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def elapsed_time_label(started_at_iso: str, now: datetime | None = None) -> str:
    try:
        started = datetime.fromisoformat(started_at_iso.replace("Z", "+00:00"))
    except ValueError:
        started = datetime.now(timezone.utc)
    current = now or datetime.now(timezone.utc)
    seconds = max(0, int((current - started).total_seconds()))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _as_mapping(payload: Any, label: str = "request") -> Mapping[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValidationError(f"The {label} must be an object.")
    return payload


def read_text(
    payload: Mapping[str, Any],
    key: str,
    label: str,
    *,
    required: bool = False,
    max_length: int = 2000,
    default: str = "",
) -> str:
    value = payload.get(key, default)
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text.")
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if required and not value:
        raise ValidationError(f"{label} is required.")
    if len(value) > max_length:
        raise ValidationError(f"{label} is too long (limit {max_length} characters).")
    return value


def read_bool(payload: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    raise ValidationError(f"{key} must be true or false.")


def parse_session_input(payload: Any) -> dict:
    data = _as_mapping(payload, "session request")
    title = read_text(data, "title", "Conversation title", required=True, max_length=120)
    customer_name = read_text(data, "customer_name", "Customer name", max_length=120)
    company = read_text(data, "company", "Company", max_length=120)
    rep_name = read_text(data, "rep_name", "Representative name", max_length=80, default="You") or "You"
    customer_language = normalize_language(data.get("customer_language"), "es")
    rep_language = normalize_language(data.get("rep_language"), "en")
    occurred_on = read_text(data, "occurred_on", "Conversation date", max_length=10, default=today_local_iso())
    if not _DATE_RE.match(occurred_on):
        raise ValidationError("Conversation date must use YYYY-MM-DD.")
    return {
        "title": title,
        "customer_name": customer_name,
        "company": company,
        "rep_name": rep_name,
        "customer_language": customer_language,
        "rep_language": rep_language,
        "occurred_on": occurred_on,
    }


def parse_utterance_input(payload: Any) -> dict:
    data = _as_mapping(payload, "utterance request")
    speaker = data.get("speaker")
    if speaker not in SPEAKERS:
        raise ValidationError("Choose Customer or Representative.")
    original = read_text(data, "original_text", "Original text", required=True, max_length=4000)
    translation = read_text(data, "translation", "Translation", max_length=4000)
    language = normalize_language(data.get("language"), "en")
    return {
        "speaker": speaker,
        "original_text": original,
        "translation": translation or None,
        "language": language,
        "display_time": normalize_time(data.get("display_time")),
    }


def _speaker_from_label(label: str, line_no: int) -> str:
    normalized = re.sub(r"\s+", " ", label.strip().lower())
    normalized = re.sub(r"\s*#?\d+$", "", normalized).strip()
    if normalized in _CUSTOMER_ALIASES:
        return "customer"
    if normalized in _REP_ALIASES:
        return "rep"
    raise ValidationError(
        f"Line {line_no}: use 'Customer:' or 'Rep:' as the speaker label.",
        detail={"line": line_no, "label": label.strip()},
    )


def parse_transcript(text: Any, default_language: str = "en") -> list[dict]:
    """Parse the simple transcript format accepted by the import dialog.

    Supported line: ``[00:42] Customer (es): Hola => Hello``
    Timestamp, language, and translation are optional. Blank lines and lines
    starting with ``#`` are ignored.
    """
    if not isinstance(text, str):
        raise ValidationError("Transcript must be text.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) > 80_000:
        raise ValidationError("Transcript is too long for one import (limit 80,000 characters).")
    default_language = normalize_language(default_language)
    rows: list[dict] = []
    for line_no, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        display_time = None
        time_match = re.match(r"^\[?(\d{1,3}:\d{2})\]?\s*", line)
        if time_match:
            display_time = normalize_time(time_match.group(1))
            line = line[time_match.end():].strip()
        label_match = re.match(r"^([^:]{1,50}):\s*(.+)$", line)
        if not label_match:
            raise ValidationError(
                f"Line {line_no}: expected 'Customer:' or 'Rep:' before the text.",
                detail={"line": line_no},
            )
        label_text = label_match.group(1).strip()
        language = default_language
        label_lang_match = re.match(
            r"^(.*?)\s*(?:\(|\[)([A-Za-z-]{2,10})(?:\)|\])\s*$", label_text
        )
        if label_lang_match:
            label_text = label_lang_match.group(1).strip()
            language = normalize_language(label_lang_match.group(2), default_language)
        speaker = _speaker_from_label(label_text, line_no)
        body = label_match.group(2).strip()
        lang_match = re.match(r"^(?:\(|\[)([A-Za-z-]{2,10})(?:\)|\])\s*", body)
        if lang_match:
            language = normalize_language(lang_match.group(1), default_language)
            body = body[lang_match.end():].strip()
        translation = None
        for delimiter in ("=>", "\u2192"):
            if delimiter in body:
                original, translation = body.split(delimiter, 1)
                body = original.strip()
                translation = translation.strip() or None
                break
        if not body:
            raise ValidationError(f"Line {line_no}: the utterance text is empty.")
        if len(body) > 4000 or (translation and len(translation) > 4000):
            raise ValidationError(f"Line {line_no}: text is too long.")
        rows.append({
            "speaker": speaker,
            "original_text": body,
            "translation": translation,
            "language": language,
            "display_time": display_time,
        })
        if len(rows) > 400:
            raise ValidationError("A single import is limited to 400 utterances.")
    if not rows:
        raise ValidationError("No transcript lines found. Add lines like 'Customer: ...'.")
    return rows


def parse_refs(payload: Mapping[str, Any], key: str = "evidence_refs") -> list[str]:
    value = payload.get(key, [])
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValidationError("Evidence must be a list of evidence IDs.")
    if len(value) > 12:
        raise ValidationError("Analyze at most 12 utterances at a time.")
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError("Evidence IDs must be text such as E-03.")
        ref = item.strip()
        if not re.match(r"^E-\d{2,4}$", ref):
            raise ValidationError("Evidence IDs must look like E-03.")
        if ref not in refs:
            refs.append(ref)
    return refs


def parse_playbook_overrides(payload: Any) -> dict:
    data = _as_mapping(payload, "playbook request")
    allowed = {
        "title", "scenario", "objection", "approved_response",
        "discovery_questions", "category",
    }
    out: dict[str, Any] = {}
    limits = {
        "title": 140,
        "scenario": 240,
        "objection": 1000,
        "approved_response": 3000,
        "category": 40,
    }
    for key, limit in limits.items():
        if key in data:
            out[key] = read_text(data, key, key.replace("_", " ").title(), max_length=limit)
    if "discovery_questions" in data:
        raw = data.get("discovery_questions")
        if raw is None:
            raw = []
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.split("\n") if part.strip()]
        if not isinstance(raw, list):
            raise ValidationError("Discovery questions must be a list.")
        questions = []
        for item in raw:
            if not isinstance(item, str):
                raise ValidationError("Each discovery question must be text.")
            item = item.strip()
            if not item:
                continue
            if len(item) > 400:
                raise ValidationError("A discovery question is too long.")
            questions.append(item)
        if len(questions) > 10:
            raise ValidationError("Use at most 10 discovery questions.")
        out["discovery_questions"] = questions
    if "category" in out and out["category"] and out["category"] not in INSIGHT_TYPES:
        raise ValidationError("Choose a valid coaching category.")
    return out


def parse_settings_input(payload: Any, current: Mapping[str, Any]) -> dict:
    data = _as_mapping(payload, "settings request")
    mode = data.get("provider_mode", current.get("provider_mode", "mock"))
    if mode not in PROVIDER_MODES:
        raise ValidationError("Choose Demo or Configured provider mode.")
    base_url = read_text(data, "base_url", "Provider base URL", max_length=300)
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValidationError("Provider base URL must be a complete http(s) URL.")
        base_url = base_url.rstrip("/")
    model = read_text(data, "model", "Provider model", max_length=140)
    try:
        timeout_s = float(data.get("timeout_s", current.get("timeout_s", 25)))
    except (TypeError, ValueError):
        raise ValidationError("Provider timeout must be a number.")
    if not 5 <= timeout_s <= 120:
        raise ValidationError("Provider timeout must be between 5 and 120 seconds.")
    reviewer_name = read_text(data, "reviewer_name", "Reviewer name", max_length=80)
    return {
        "provider_mode": mode,
        "base_url": base_url,
        "model": model,
        "timeout_s": timeout_s,
        "reviewer_name": reviewer_name,
    }


def ensure_reviewer(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Enter the reviewer name before approving.")
    reviewer = value.strip()
    if len(reviewer) > 80:
        raise ValidationError("Reviewer name is too long.")
    return reviewer


def clean_optional_text(value: Any, *, max_length: int = 2000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError("Expected text.")
    value = value.replace("\r\n", "\n").strip()
    if len(value) > max_length:
        raise ValidationError(f"Text is too long (limit {max_length} characters).")
    return value
