from __future__ import annotations

import json

import pytest

from clearcommit_teams.context import build_context
from clearcommit_teams.errors import (
    InsufficientEvidenceError,
    InvalidModelOutputError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ValidationError,
)
from clearcommit_teams.models import INSIGHT_TYPES
from tests.support import StubProvider, answer_json, coach_json, insight


def context_with(data_dir, provider: StubProvider):
    return build_context(
        data_dir,
        env={"CLEARCOMMIT_TEAMS_SEED_SAMPLES": "1"},
        provider_factory=lambda settings: provider,
    )


def run_count(ctx) -> int:
    with ctx.db.connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0])


def test_mock_coach_returns_evidence_linked_insights(ctx) -> None:
    refs = [f"E-{index:02d}" for index in range(1, 11)]
    result = ctx.service.analyze("s_sample_helio", refs)
    assert result["provider"]["mode"] == "mock"
    assert result["provider"]["name"] == "Demo coach (rule-based)"
    assert 1 <= len(result["insights"]) <= 8
    utterances = {
        item["ref"]: item for item in ctx.repo.get_session("s_sample_helio")["utterances"]
    }
    assert {item["type"] for item in result["insights"]} == set(INSIGHT_TYPES)
    for item in result["insights"]:
        assert item["evidence"]
        for evidence in item["evidence"]:
            source = utterances[evidence["ref"]]
            assert evidence["quote"] == source["original_text"]
            assert evidence["utterance_id"] == source["id"]
        assert item["proposed_alternative"].strip()
        assert item["limitations"].strip()
    assert result["run"]["evidence_refs"] == refs


def test_mock_assistant_cites_selected_evidence(ctx) -> None:
    note = ctx.service.ask(
        "s_sample_helio",
        ["E-01", "E-03"],
        "What discovery question should I ask next?",
    )
    assert [item["ref"] for item in note["evidence"]] == ["E-01", "E-03"]
    assert "E-01" in note["answer"]
    assert note["provider_mode"] == "mock"
    assert ctx.repo.list_assistant_notes("s_sample_helio")[0]["id"] == note["id"]


@pytest.mark.parametrize("refs", [[], None])
def test_analyze_requires_evidence(data_dir, refs) -> None:
    stub = StubProvider()
    ctx = context_with(data_dir, stub)
    with pytest.raises(InsufficientEvidenceError):
        ctx.service.analyze("s_sample_helio", refs)  # type: ignore[arg-type]
    assert stub.coach_calls == 0
    assert run_count(ctx) == 0


def test_analyze_rejects_unknown_or_foreign_evidence(data_dir) -> None:
    stub = StubProvider()
    ctx = context_with(data_dir, stub)
    with pytest.raises(ValidationError):
        ctx.service.analyze("s_sample_helio", ["E-99"])
    with pytest.raises(ValidationError):
        ctx.service.analyze("s_sample_northwind", ["E-08", "E-09"])
    assert stub.coach_calls == 0


def test_analyze_enforces_evidence_limit(data_dir) -> None:
    stub = StubProvider()
    ctx = context_with(data_dir, stub)
    with pytest.raises(ValidationError):
        ctx.service.analyze("s_sample_helio", [f"E-{index:02d}" for index in range(1, 13)])
    assert stub.coach_calls == 0


@pytest.mark.parametrize(
    "raw",
    [
        "this is not json",
        "[]",
        json.dumps({"summary": "x", "limitations": "y"}),
        coach_json([insight(refs=["E-09"])]),
        coach_json([insight(observation="The customer is worried about the price.")]),
        coach_json([insight(kind="other")]),
        coach_json([insight(confidence="certain")]),
        coach_json([insight() for _ in range(9)]),
        coach_json([{"type": "objection"}]),
        json.dumps({"summary": "", "limitations": "y", "insights": []}),
    ],
)
def test_invalid_model_output_is_rejected_and_not_persisted(data_dir, raw: str) -> None:
    stub = StubProvider(coach_raw=raw)
    ctx = context_with(data_dir, stub)
    with pytest.raises(InvalidModelOutputError):
        ctx.service.analyze("s_sample_helio", ["E-01"])
    assert stub.coach_calls == 1
    assert run_count(ctx) == 0
    assert ctx.repo.list_insights("s_sample_helio") == []


def test_code_fenced_json_is_accepted(data_dir) -> None:
    raw = "```json\n" + coach_json() + "\n```"
    ctx = context_with(data_dir, StubProvider(coach_raw=raw))
    result = ctx.service.analyze("s_sample_helio", ["E-01"])
    assert len(result["insights"]) == 1


def test_empty_insights_with_summary_is_valid(data_dir) -> None:
    raw = json.dumps({
        "summary": "Nothing crossed the threshold in this fragment.",
        "limitations": "One fragment is not the whole conversation.",
        "insights": [],
    })
    ctx = context_with(data_dir, StubProvider(coach_raw=raw))
    result = ctx.service.analyze("s_sample_helio", ["E-01"])
    assert result["insights"] == []
    assert run_count(ctx) == 1


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ProviderTimeoutError("timed out"), "provider_timeout"),
        (ProviderRateLimitError("slow down"), "provider_rate_limit"),
        (ProviderUnavailableError("offline"), "provider_unavailable"),
        (ProviderAuthError("bad key"), "provider_auth"),
    ],
)
def test_provider_errors_propagate_without_saving(data_dir, error, code: str) -> None:
    stub = StubProvider(coach_error=error)
    ctx = context_with(data_dir, stub)
    with pytest.raises(type(error)) as excinfo:
        ctx.service.analyze("s_sample_helio", ["E-01"])
    assert excinfo.value.code == code
    assert run_count(ctx) == 0


def test_unexpected_provider_exception_is_wrapped(data_dir) -> None:
    stub = StubProvider(coach_error=RuntimeError("boom"))
    ctx = context_with(data_dir, stub)
    with pytest.raises(ProviderError) as excinfo:
        ctx.service.analyze("s_sample_helio", ["E-01"])
    assert excinfo.value.code == "provider_error"
    assert "boom" not in excinfo.value.message
    assert run_count(ctx) == 0


def test_reanalysis_replaces_run_for_same_evidence(data_dir) -> None:
    stub = StubProvider()
    ctx = context_with(data_dir, stub)
    first = ctx.service.analyze("s_sample_helio", ["E-01", "E-02"])
    second = ctx.service.analyze("s_sample_helio", ["E-01", "E-02"])
    assert first["run"]["id"] != second["run"]["id"]
    assert run_count(ctx) == 1
    assert len(ctx.repo.list_insights("s_sample_helio")) == 1


def test_assistant_rejects_uncited_or_miscited_answers(data_dir) -> None:
    cases = [
        answer_json(answer="The customer is ready to renew.", refs=["E-01"]),
        answer_json(answer="The price came up. [E-09]", refs=["E-09"]),
        answer_json(answer="The price came up. [E-01]", refs=["E-01", "E-02"]),
        answer_json(answer="The price came up.", refs=["E-01"]),
    ]
    for raw in cases:
        stub = StubProvider(answer_raw=raw)
        ctx = context_with(data_dir, stub)
        with pytest.raises(InvalidModelOutputError):
            ctx.service.ask("s_sample_helio", ["E-01", "E-02"], "What happened?")
        assert ctx.repo.list_assistant_notes("s_sample_helio") == []


def test_assistant_requires_a_question_and_evidence(data_dir) -> None:
    stub = StubProvider()
    ctx = context_with(data_dir, stub)
    with pytest.raises(ValidationError):
        ctx.service.ask("s_sample_helio", ["E-01"], "   ")
    with pytest.raises(InsufficientEvidenceError):
        ctx.service.ask("s_sample_helio", [], "What happened?")
    with pytest.raises(ValidationError):
        ctx.service.ask("s_sample_helio", [f"E-{i:02d}" for i in range(1, 8)], "What happened?")
    assert stub.answer_calls == 0


def test_assistant_provider_failure_is_not_persisted(data_dir) -> None:
    stub = StubProvider(answer_error=ProviderTimeoutError("timed out"))
    ctx = context_with(data_dir, stub)
    with pytest.raises(ProviderTimeoutError):
        ctx.service.ask("s_sample_helio", ["E-01"], "What happened?")
    assert ctx.repo.list_assistant_notes("s_sample_helio") == []
