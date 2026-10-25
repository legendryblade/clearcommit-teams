"""Provider selection and honest configuration status."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from ..errors import ProviderNotConfiguredError
from .base import CoachProvider
from .mock import MockCoachProvider
from .openai_compat import HttpTransport, OpenAICompatibleConfig, OpenAICompatibleProvider

API_KEY_ENV = "CLEARCOMMIT_TEAMS_API_KEY"


@dataclass(frozen=True)
class ProviderSettings:
    provider_mode: str = "mock"
    base_url: str = ""
    model: str = ""
    timeout_s: float = 25.0

    @classmethod
    def from_dict(cls, values: Mapping) -> "ProviderSettings":
        try:
            timeout = float(values.get("timeout_s", 25))
        except (TypeError, ValueError):
            timeout = 25.0
        return cls(
            provider_mode=str(values.get("provider_mode", "mock") or "mock"),
            base_url=str(values.get("base_url", "") or "").strip().rstrip("/"),
            model=str(values.get("model", "") or "").strip(),
            timeout_s=timeout,
        )


def _api_key(env: Mapping[str, str] | None) -> str:
    source = os.environ if env is None else env
    return str(source.get(API_KEY_ENV, "") or "").strip()


def provider_status(settings: ProviderSettings, env: Mapping[str, str] | None = None) -> dict:
    key_present = bool(_api_key(env))
    if settings.provider_mode == "mock":
        return {
            "mode": "mock",
            "mode_label": "Demo coach · rule-based",
            "demo": True,
            "configured": True,
            "network_required": False,
            "provider_name": "Demo coach (rule-based)",
            "model": "rules-v1",
            "base_url": "",
            "key_env": API_KEY_ENV,
            "key_present": key_present,
            "missing": [],
            "limitations": (
                "Deterministic rules, sample conversations, and a local database. No audio capture "
                "and no model calls."
            ),
        }

    missing = []
    if not key_present:
        missing.append(f"API key (set {API_KEY_ENV} in the environment)")
    if not settings.base_url:
        missing.append("Base URL")
    if not settings.model:
        missing.append("Model name")
    configured = not missing
    return {
        "mode": "openai_compatible",
        "mode_label": "Configured provider",
        "demo": False,
        "configured": configured,
        "network_required": True,
        "provider_name": "OpenAI-compatible provider" if not settings.base_url else (
            "OpenAI-compatible · " + settings.base_url.split("://", 1)[-1].split("/", 1)[0]
        ),
        "model": settings.model,
        "base_url": settings.base_url,
        "key_env": API_KEY_ENV,
        "key_present": key_present,
        "missing": missing,
        "limitations": (
            "Sends the selected transcript text to the configured endpoint. No audio is sent. "
            "The API key is read from the environment and never stored by this app."
        ),
    }


def build_provider(
    settings: ProviderSettings,
    *,
    env: Mapping[str, str] | None = None,
    transport: HttpTransport | None = None,
) -> CoachProvider:
    if settings.provider_mode == "mock":
        return MockCoachProvider()
    status = provider_status(settings, env)
    if not status["configured"]:
        raise ProviderNotConfiguredError(
            "The configured provider is incomplete: " + "; ".join(status["missing"]) + ".",
            detail={"missing": status["missing"], "key_env": API_KEY_ENV},
        )
    config = OpenAICompatibleConfig(
        base_url=settings.base_url,
        model=settings.model,
        api_key=_api_key(env),
        timeout_s=settings.timeout_s,
    )
    return OpenAICompatibleProvider(config, transport=transport)
