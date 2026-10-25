from __future__ import annotations

import pytest

from clearcommit_teams.errors import ValidationError
from clearcommit_teams.models import (
    evidence_ref,
    language_pair_label,
    normalize_language,
    parse_playbook_overrides,
    parse_refs,
    parse_session_input,
    parse_settings_input,
    parse_transcript,
    parse_utterance_input,
)


def test_transcript_parser_reads_timestamp_language_and_translation() -> None:
    rows = parse_transcript(
        "[00:42] Customer (es): Hola, el precio nos preocupa => Hello, the price concerns us\n"
        "Rep: I understand.\n"
        "# a comment\n"
    )
    assert len(rows) == 2
    assert rows[0] == {
        "speaker": "customer",
        "original_text": "Hola, el precio nos preocupa",
        "translation": "Hello, the price concerns us",
        "language": "es",
        "display_time": "00:42",
    }
    assert rows[1]["speaker"] == "rep"
    assert rows[1]["translation"] is None
    assert rows[1]["language"] == "en"


def test_transcript_parser_accepts_arrow_translation_and_aliases() -> None:
    rows = parse_transcript("Sales: We can help \u2192 Podemos ayudar")
    assert rows[0]["speaker"] == "rep"
    assert rows[0]["original_text"] == "We can help"
    assert rows[0]["translation"] == "Podemos ayudar"


def test_transcript_parser_rejects_unknown_speaker_with_line_number() -> None:
    with pytest.raises(ValidationError) as excinfo:
        parse_transcript("Customer: Hola\nManager: Hello")
    assert "Line 2" in excinfo.value.message
    assert excinfo.value.detail["line"] == 2


@pytest.mark.parametrize("text", ["", "   \n# only comments\n", "Customer:"])
def test_transcript_parser_rejects_empty_imports(text: str) -> None:
    with pytest.raises(ValidationError):
        parse_transcript(text)


def test_transcript_parser_rejects_oversized_import() -> None:
    with pytest.raises(ValidationError):
        parse_transcript("Customer: " + ("x" * 80_001))


def test_utterance_validation_requires_speaker_and_text() -> None:
    with pytest.raises(ValidationError):
        parse_utterance_input({"speaker": "manager", "original_text": "Hi"})
    with pytest.raises(ValidationError):
        parse_utterance_input({"speaker": "customer", "original_text": "  "})
    parsed = parse_utterance_input({
        "speaker": "customer",
        "original_text": "Hola",
        "language": "ES",
        "display_time": "1:05",
    })
    assert parsed["language"] == "es"
    assert parsed["display_time"] == "01:05"


def test_session_validation_defaults_are_demo_friendly() -> None:
    parsed = parse_session_input({"title": "  Renewal call  "})
    assert parsed["title"] == "Renewal call"
    assert parsed["customer_language"] == "es"
    assert parsed["rep_language"] == "en"
    assert parsed["rep_name"] == "You"
    with pytest.raises(ValidationError):
        parse_session_input({"title": ""})
    with pytest.raises(ValidationError):
        parse_session_input({"title": "Call", "occurred_on": "10/24/2026"})


def test_language_and_pair_labels() -> None:
    assert normalize_language("PT-BR") == "pt-br"
    assert language_pair_label("es", "en") == "Spanish \u2194 English"
    assert language_pair_label("en", "en") == "English"
    with pytest.raises(ValidationError):
        normalize_language("not a language")


def test_evidence_refs_are_stable_and_validated() -> None:
    assert evidence_ref(1) == "E-01"
    assert evidence_ref(42) == "E-42"
    assert parse_refs({"evidence_refs": ["E-02", "E-03", "E-02"]}) == ["E-02", "E-03"]
    with pytest.raises(ValidationError):
        parse_refs({"evidence_refs": ["2"]})
    with pytest.raises(ValidationError):
        parse_refs({"evidence_refs": "E-01"})


def test_settings_validation() -> None:
    current = {"provider_mode": "mock", "timeout_s": 25.0}
    parsed = parse_settings_input({
        "provider_mode": "openai_compatible",
        "base_url": "https://example.test/v1/",
        "model": "example-model",
        "timeout_s": "30",
    }, current)
    assert parsed["base_url"] == "https://example.test/v1"
    assert parsed["timeout_s"] == 30.0
    with pytest.raises(ValidationError):
        parse_settings_input({"base_url": "not-a-url"}, current)
    with pytest.raises(ValidationError):
        parse_settings_input({"timeout_s": 2}, current)
    with pytest.raises(ValidationError):
        parse_settings_input({"provider_mode": "cloud"}, current)


def test_playbook_overrides_accept_multiline_questions() -> None:
    parsed = parse_playbook_overrides({
        "title": "Handle price concern",
        "discovery_questions": "What budget was approved?\nWho signs?",
        "category": "objection",
    })
    assert parsed["discovery_questions"] == ["What budget was approved?", "Who signs?"]
    with pytest.raises(ValidationError):
        parse_playbook_overrides({"category": "unknown"})
