"""Provider contracts for coaching and grounded assistant answers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EvidenceItem:
    ref: str
    speaker: str
    original_text: str
    translation: str | None
    language: str
    display_time: str | None

    def as_prompt_block(self) -> str:
        label = "Customer" if self.speaker == "customer" else "Representative"
        translation = f'\n  Translation: "{self.translation}"' if self.translation else ""
        return (
            f'[{self.ref}] {self.display_time or "time not given"} | {label} ({self.language})\n'
            f'  Original: "{self.original_text}"{translation}'
        )


@dataclass(frozen=True)
class CoachRequest:
    evidence: tuple[EvidenceItem, ...]

    @property
    def allowed_refs(self) -> set[str]:
        return {item.ref for item in self.evidence}


@dataclass(frozen=True)
class AssistantRequest:
    question: str
    evidence: tuple[EvidenceItem, ...]

    @property
    def allowed_refs(self) -> set[str]:
        return {item.ref for item in self.evidence}


@dataclass(frozen=True)
class ProviderDescriptor:
    mode: str
    name: str
    model: str


class CoachProvider(Protocol):
    descriptor: ProviderDescriptor

    def generate_coaching(self, request: CoachRequest) -> str:
        """Return raw JSON text. Validation happens outside the provider."""

    def generate_answer(self, request: AssistantRequest) -> str:
        """Return raw JSON text for a grounded note."""

    def test_connection(self) -> dict:
        """Optionally contact the provider. Must be user-triggered."""
