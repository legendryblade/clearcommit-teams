from __future__ import annotations

import json
from typing import Any

from clearcommit_teams.providers.base import ProviderDescriptor


def insight(
    *,
    kind: str = "objection",
    refs: list[str] | None = None,
    observation: str = "The customer raised the price of the annual plan.",
    title: str = "Price concern",
    alternative: str = "What would make the annual plan easier to approve?",
    confidence: str = "high",
) -> dict:
    return {
        "type": kind,
        "title": title,
        "evidence_refs": refs or ["E-01"],
        "observation": observation,
        "why_it_matters": "The concern needs a direct answer before the close.",
        "proposed_alternative": alternative,
        "limitations": "The selected text is the only evidence available.",
        "recommended_action": "Ask one open question before responding.",
        "confidence": confidence,
    }


def coach_json(
    insights: list[dict] | None = None,
    *,
    summary: str = "The customer raised a price concern.",
    limitations: str = "Only the selected transcript is visible.",
) -> str:
    return json.dumps({
        "summary": summary,
        "limitations": limitations,
        "insights": insights if insights is not None else [insight()],
    }, ensure_ascii=False)


def answer_json(
    answer: str = "The customer asked about the annual price. [E-01]",
    refs: list[str] | None = None,
    limitations: str = "Only the selected transcript is visible.",
) -> str:
    return json.dumps({
        "answer": answer,
        "evidence_refs": refs if refs is not None else ["E-01"],
        "limitations": limitations,
    }, ensure_ascii=False)


class StubProvider:
    descriptor = ProviderDescriptor(
        mode="openai_compatible",
        name="Stub provider",
        model="stub-model",
    )

    def __init__(
        self,
        *,
        coach_raw: Any = None,
        answer_raw: Any = None,
        coach_error: BaseException | None = None,
        answer_error: BaseException | None = None,
    ) -> None:
        self.coach_raw = coach_raw if coach_raw is not None else coach_json()
        self.answer_raw = answer_raw if answer_raw is not None else answer_json()
        self.coach_error = coach_error
        self.answer_error = answer_error
        self.coach_calls = 0
        self.answer_calls = 0

    def generate_coaching(self, request) -> Any:
        self.coach_calls += 1
        if self.coach_error is not None:
            raise self.coach_error
        return self.coach_raw

    def generate_answer(self, request) -> Any:
        self.answer_calls += 1
        if self.answer_error is not None:
            raise self.answer_error
        return self.answer_raw

    def test_connection(self) -> dict:
        return {"ok": True, "message": "Stub provider responded.", "network": True}
