"""Coaching orchestration and deterministic output validation."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Mapping

from .repository import Repository
from .errors import (
    AppError,
    InsufficientEvidenceError,
    InvalidModelOutputError,
    ProviderError,
    ValidationError,
)
from .models import CONFIDENCE_LEVELS, INSIGHT_TYPES, SPEAKER_LABELS
from .providers import (
    AssistantRequest,
    CoachRequest,
    EvidenceItem,
    ProviderDescriptor,
    ProviderSettings,
    build_provider,
)

MAX_INSIGHTS = 8
MAX_EVIDENCE = 12
MAX_ASSISTANT_EVIDENCE = 6

# Assertions about a customer's hidden mental state are not evidence. A model
# that makes them is rejected rather than shown as grounded coaching.
_INTENT_PATTERNS = (
    re.compile(
        r"\b(the customer|the client|they|she|he)\s+(is|are|seems|appears|must be|may be)\s+"
        r"(worried|afraid|frustrated|angry|hesitant|ready|interested|unhappy|happy|confused|"
        r"excited|receptive|skeptical|upset|annoyed)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(the customer|the client|they|she|he)\s+(wants?|intends?|plans?|feels?|thinks?|"
        r"believes?|expects?|needs?|is trying)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(the customer's|the client's)\s+(intent|motivation|motive|feeling|goal|state of mind)\b",
        re.IGNORECASE,
    ),
)

_CITATION_RE = re.compile(r"\[(E-\d{2,4})\]")


def _intent_claim(text: str) -> str | None:
    for pattern in _INTENT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def parse_model_json(raw: Any) -> dict:
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidModelOutputError("The provider returned no coaching content.")
    text = _strip_code_fence(raw)
    if len(text) > 200_000:
        raise InvalidModelOutputError("The provider returned an oversized response.")
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise InvalidModelOutputError(
            "The provider did not return valid JSON. Retry or choose a stronger model."
        ) from exc
    if not isinstance(data, dict):
        raise InvalidModelOutputError("The provider returned JSON in the wrong shape.")
    return data


def _text(data: Mapping, key: str, label: str, *, max_length: int) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidModelOutputError(f"The provider output is missing {label}.")
    value = re.sub(r"\s+", " ", value.strip())
    if len(value) > max_length:
        raise InvalidModelOutputError(f"The provider output has an oversized {label}.")
    return value


def _refs(value: Any, allowed: set[str], field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise InvalidModelOutputError(f"Every insight needs at least one evidence ID ({field}).")
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str) or not re.match(r"^E-\d{2,4}$", item.strip()):
            raise InvalidModelOutputError("The provider returned an invalid evidence ID.")
        ref = item.strip()
        if ref not in allowed:
            raise InvalidModelOutputError(
                "The provider cited evidence that was not supplied; the result was rejected.",
                detail={"unknown_ref": ref},
            )
        if ref not in refs:
            refs.append(ref)
    return refs


def validate_coach_output(raw: Any, request: CoachRequest) -> dict:
    data = parse_model_json(raw)
    summary = _text(data, "summary", "a summary", max_length=1200)
    limitations = _text(data, "limitations", "overall limitations", max_length=1200)
    raw_insights = data.get("insights")
    if not isinstance(raw_insights, list):
        raise InvalidModelOutputError("The provider output is missing the insights list.")
    if len(raw_insights) > MAX_INSIGHTS:
        raise InvalidModelOutputError(
            f"The provider returned more than {MAX_INSIGHTS} insights; the result was rejected."
        )
    allowed = request.allowed_refs
    insights: list[dict] = []
    seen: set[tuple] = set()
    for item in raw_insights:
        if not isinstance(item, dict):
            raise InvalidModelOutputError("An insight was not an object.")
        kind = item.get("type")
        if kind not in INSIGHT_TYPES:
            raise InvalidModelOutputError("The provider returned an unknown insight type.")
        title = _text(item, "title", "a title", max_length=140)
        observation = _text(item, "observation", "an observation", max_length=900)
        why = _text(item, "why_it_matters", "a why-it-matters explanation", max_length=900)
        alternative = _text(item, "proposed_alternative", "a proposed alternative", max_length=1400)
        insight_limits = _text(item, "limitations", "an insight limitation", max_length=800)
        action = _text(item, "recommended_action", "a recommended action", max_length=600)
        confidence = item.get("confidence")
        if confidence not in CONFIDENCE_LEVELS:
            raise InvalidModelOutputError("The provider returned an invalid confidence level.")
        refs = _refs(item.get("evidence_refs"), allowed, "evidence_refs")
        for field_name, field_text in (
            ("title", title),
            ("observation", observation),
            ("why_it_matters", why),
        ):
            claim = _intent_claim(field_text)
            if claim:
                raise InvalidModelOutputError(
                    "The provider asserted a customer's hidden intention; the result was rejected.",
                    detail={"field": field_name, "claim": claim},
                )
        key = (kind, tuple(sorted(refs)), observation.lower())
        if key in seen:
            continue
        seen.add(key)
        insights.append({
            "type": kind,
            "title": title,
            "evidence_refs": refs,
            "observation": observation,
            "why_it_matters": why,
            "proposed_alternative": alternative,
            "limitations": insight_limits,
            "recommended_action": action,
            "confidence": confidence,
        })
    return {"summary": summary, "limitations": limitations, "insights": insights}


def validate_assistant_output(raw: Any, request: AssistantRequest) -> dict:
    data = parse_model_json(raw)
    answer = _text(data, "answer", "an answer", max_length=3000)
    limitations = _text(data, "limitations", "assistant limitations", max_length=1000)
    refs = _refs(data.get("evidence_refs"), request.allowed_refs, "evidence_refs")
    citations = set(_CITATION_RE.findall(answer))
    unknown = citations - request.allowed_refs
    if unknown:
        raise InvalidModelOutputError(
            "The assistant cited evidence that was not supplied; the answer was rejected.",
            detail={"unknown_refs": sorted(unknown)},
        )
    if not citations:
        raise InvalidModelOutputError("The assistant answer did not cite its evidence.")
    if set(refs) != citations:
        raise InvalidModelOutputError(
            "The assistant's declared evidence does not match the citations in its answer."
        )
    return {"answer": answer, "limitations": limitations, "evidence_refs": refs}


def evidence_items(rows: list[dict]) -> tuple[EvidenceItem, ...]:
    return tuple(
        EvidenceItem(
            ref=row["ref"],
            speaker=row["speaker"],
            original_text=row["original_text"],
            translation=row.get("translation"),
            language=row["language"],
            display_time=row.get("display_time"),
        )
        for row in rows
    )


def _descriptor_payload(descriptor: ProviderDescriptor) -> dict:
    return {"mode": descriptor.mode, "name": descriptor.name, "model": descriptor.model}


class CoachingService:
    def __init__(
        self,
        repo: Repository,
        *,
        provider_factory: Callable[[ProviderSettings], Any] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.repo = repo
        self._provider_factory = provider_factory or (
            lambda settings: build_provider(settings, env=env)
        )

    def _provider(self):
        settings = ProviderSettings.from_dict(self.repo.settings())
        return self._provider_factory(settings)

    def analyze(self, session_id: Any, refs: list[str]) -> dict:
        if not isinstance(session_id, str) or not session_id:
            raise ValidationError("A conversation ID is required.")
        if not refs:
            raise InsufficientEvidenceError(
                "Select at least one finalized utterance before asking the coach to analyze."
            )
        if len(refs) > MAX_EVIDENCE:
            raise ValidationError(f"Analyze at most {MAX_EVIDENCE} utterances at a time.")
        rows = self.repo.resolve_evidence(session_id, refs)
        if not rows or all(not row["original_text"].strip() for row in rows):
            raise InsufficientEvidenceError(
                "The selected evidence has no usable text. Add or select a finalized utterance."
            )
        request = CoachRequest(evidence=evidence_items(rows))
        provider = self._provider()
        started = time.monotonic()
        try:
            raw = provider.generate_coaching(request)
        except AppError:
            raise
        except Exception as exc:
            raise ProviderError("The provider call failed unexpectedly.") from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        result = validate_coach_output(raw, request)
        saved = self.repo.save_analysis(
            session_id=session_id,
            provider_mode=provider.descriptor.mode,
            provider_name=provider.descriptor.name,
            model=provider.descriptor.model,
            evidence=rows,
            summary=result["summary"],
            limitations=result["limitations"],
            duration_ms=duration_ms,
            insights=result["insights"],
        )
        saved["provider"] = _descriptor_payload(provider.descriptor)
        return saved

    def ask(self, session_id: Any, refs: list[str], question: Any) -> dict:
        if not isinstance(session_id, str) or not session_id:
            raise ValidationError("A conversation ID is required.")
        if not isinstance(question, str) or not question.strip():
            raise ValidationError("Type a question about the selected evidence.")
        question = question.strip()
        if len(question) > 600:
            raise ValidationError("Questions are limited to 600 characters.")
        if not refs:
            raise InsufficientEvidenceError(
                "Select at least one utterance before asking the assistant."
            )
        if len(refs) > MAX_ASSISTANT_EVIDENCE:
            raise ValidationError(
                f"Ask about at most {MAX_ASSISTANT_EVIDENCE} utterances at a time."
            )
        rows = self.repo.resolve_evidence(session_id, refs)
        if not rows:
            raise InsufficientEvidenceError("The selected evidence could not be found.")
        request = AssistantRequest(question=question, evidence=evidence_items(rows))
        provider = self._provider()
        try:
            raw = provider.generate_answer(request)
        except AppError:
            raise
        except Exception as exc:
            raise ProviderError("The provider call failed unexpectedly.") from exc
        result = validate_assistant_output(raw, request)
        note = self.repo.save_assistant_note(
            session_id=session_id,
            question=question,
            answer=result["answer"],
            limitations=result["limitations"],
            provider_mode=provider.descriptor.mode,
            provider_name=provider.descriptor.name,
            model=provider.descriptor.model,
            evidence=rows,
        )
        note["provider"] = _descriptor_payload(provider.descriptor)
        return note
