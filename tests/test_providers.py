from __future__ import annotations

import json
import socket
from urllib.error import URLError

import pytest

from clearcommit_teams.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from clearcommit_teams.providers import (
    API_KEY_ENV,
    AssistantRequest,
    CoachRequest,
    EvidenceItem,
    MockCoachProvider,
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
    ProviderSettings,
    UrllibTransport,
    build_provider,
    provider_status,
)

KEY = "sk-test-secret-value"
CONFIGURED = ProviderSettings(
    provider_mode="openai_compatible",
    base_url="https://provider.example/v1",
    model="example-model",
    timeout_s=20,
)


def evidence() -> tuple[EvidenceItem, ...]:
    return (
        EvidenceItem(
            ref="E-01",
            speaker="customer",
            original_text="El precio nos preocupa.",
            translation="The price concerns us.",
            language="es",
            display_time="00:10",
        ),
    )


def completion(content: str) -> str:
    return json.dumps({"choices": [{"message": {"content": content}}]})


class FakeTransport:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    def post_json(self, url, headers, payload, timeout_s):
        self.calls.append({
            "url": url,
            "headers": dict(headers),
            "payload": payload,
            "timeout_s": timeout_s,
        })
        response = self.responses.pop(0) if self.responses else (500, "")
        if isinstance(response, BaseException):
            raise response
        return response


def provider(transport: FakeTransport, *, key: str = KEY) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        OpenAICompatibleConfig(
            base_url=CONFIGURED.base_url,
            model=CONFIGURED.model,
            api_key=key,
            timeout_s=CONFIGURED.timeout_s,
            retry_delay_s=0,
        ),
        transport=transport,
    )


def test_mock_status_is_explicit_and_offline() -> None:
    status = provider_status(ProviderSettings(), env={})
    assert status["mode"] == "mock"
    assert status["demo"] is True
    assert status["network_required"] is False
    assert status["configured"] is True
    assert status["model"] == "rules-v1"


def test_real_status_lists_missing_configuration_without_the_key() -> None:
    status = provider_status(CONFIGURED, env={})
    assert status["configured"] is False
    assert status["network_required"] is True
    assert any(API_KEY_ENV in item for item in status["missing"])
    assert status["key_present"] is False

    configured = provider_status(CONFIGURED, env={API_KEY_ENV: KEY})
    assert configured["configured"] is True
    assert configured["key_present"] is True
    assert KEY not in json.dumps(configured)


def test_build_provider_selects_mock_or_real() -> None:
    assert isinstance(build_provider(ProviderSettings(), env={}), MockCoachProvider)
    with pytest.raises(ProviderNotConfiguredError):
        build_provider(CONFIGURED, env={})
    real = build_provider(CONFIGURED, env={API_KEY_ENV: KEY}, transport=FakeTransport([]))
    assert isinstance(real, OpenAICompatibleProvider)
    assert real.descriptor.mode == "openai_compatible"
    assert real.descriptor.name == "OpenAI-compatible · provider.example"
    assert real.descriptor.model == "example-model"


def test_request_sends_key_only_in_header_and_only_selected_text() -> None:
    transport = FakeTransport([(200, completion('{"ok":true}'))])
    result = provider(transport).generate_coaching(CoachRequest(evidence=evidence()))
    assert result == '{"ok":true}'
    call = transport.calls[0]
    assert call["url"] == "https://provider.example/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    serialized = json.dumps(call["payload"])
    assert KEY not in serialized
    assert "El precio nos preocupa." in serialized
    assert call["payload"]["model"] == "example-model"
    assert call["timeout_s"] == 20


def test_base_url_already_ending_in_chat_completions_is_not_duplicated() -> None:
    config = OpenAICompatibleConfig(
        base_url="https://provider.example/v1/chat/completions",
        model="m",
        api_key=KEY,
    )
    assert config.endpoint() == "https://provider.example/v1/chat/completions"


def test_content_list_response_is_flattened() -> None:
    body = json.dumps({"choices": [{"message": {"content": [
        {"type": "text", "text": "Hello "}, {"type": "text", "text": "team"},
    ]}}]})
    result = provider(FakeTransport([(200, body)])).generate_answer(
        AssistantRequest(question="What happened?", evidence=evidence())
    )
    assert result == "Hello team"


def test_retry_succeeds_after_one_server_error() -> None:
    transport = FakeTransport([(502, ""), (200, completion('{"ok":true}'))])
    assert provider(transport).generate_coaching(CoachRequest(evidence=evidence()))
    assert len(transport.calls) == 2


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ((401, ""), ProviderAuthError),
        ((403, ""), ProviderAuthError),
        ((429, ""), ProviderRateLimitError),
        ((400, ""), ProviderError),
        ((404, ""), ProviderError),
        ((500, ""), ProviderUnavailableError),
        ((418, ""), ProviderError),
        ((200, "not json"), ProviderUnavailableError),
        ((200, json.dumps({"choices": []})), ProviderUnavailableError),
        ((200, completion("   ")), ProviderUnavailableError),
    ],
)
def test_provider_http_failures_are_typed(response, expected) -> None:
    transport = FakeTransport([response, response])
    with pytest.raises(expected):
        provider(transport).generate_coaching(CoachRequest(evidence=evidence()))


def test_timeout_is_typed() -> None:
    transport = FakeTransport([ProviderTimeoutError("timed out")])
    with pytest.raises(ProviderTimeoutError):
        provider(transport).generate_coaching(CoachRequest(evidence=evidence()))


def test_missing_key_refuses_before_network() -> None:
    transport = FakeTransport([])
    with pytest.raises(ProviderNotConfiguredError):
        provider(transport, key="").generate_coaching(CoachRequest(evidence=evidence()))
    assert transport.calls == []


def test_test_connection_reports_success_and_failure_without_raising() -> None:
    ok = provider(FakeTransport([(200, completion('{"ok":true}'))])).test_connection()
    assert ok["ok"] is True
    assert ok["network"] is True

    failed = provider(FakeTransport([(401, "")])).test_connection()
    assert failed["ok"] is False
    assert failed["code"] == "provider_auth"
    assert failed["network"] is True


def test_urllib_transport_maps_timeout(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise socket.timeout("slow")

    monkeypatch.setattr("clearcommit_teams.providers.openai_compat.urlopen", fake_urlopen)
    with pytest.raises(ProviderTimeoutError):
        UrllibTransport().post_json("https://example.test", {}, {}, 5)


def test_urllib_transport_maps_unreachable(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise URLError("no route")

    monkeypatch.setattr("clearcommit_teams.providers.openai_compat.urlopen", fake_urlopen)
    with pytest.raises(ProviderUnavailableError):
        UrllibTransport().post_json("https://example.test", {}, {}, 5)


def test_mock_provider_meets_the_provider_contract() -> None:
    mock = MockCoachProvider()
    assert mock.descriptor.mode == "mock"
    assert mock.descriptor.name == "Demo coach (rule-based)"
    raw = mock.generate_coaching(CoachRequest(evidence=evidence()))
    parsed = json.loads(raw)
    assert parsed["insights"]
    assert parsed["insights"][0]["evidence_refs"] == ["E-01"]
    answer = json.loads(mock.generate_answer(
        AssistantRequest(question="What should I ask?", evidence=evidence())
    ))
    assert "[E-01]" in answer["answer"]
    assert mock.test_connection()["ok"] is True
