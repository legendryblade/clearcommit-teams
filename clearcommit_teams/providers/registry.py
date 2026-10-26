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
# A GROQ key is accepted directly, so the documented provider env works too.
FALLBACK_KEY_ENVS = ("GROQ_API_KEY",)
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-20b"


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
    primary = str(source.get(API_KEY_ENV, "") or "").strip()
    if primary:
        return primary
    for name in FALLBACK_KEY_ENVS:
        value = str(source.get(name, "") or "").strip()
        if value:
            return value
    return ""


def provider_status(settings: ProviderSettings, env: Mapping[str, str] | None = None) -> dict:
    key_present = bool(_api_key(env))
    source = os.environ if env is None else env
    groq_present = bool(str(source.get("GROQ_API_KEY", "") or "").strip())
    if settings.provider_mode == "mock" and groq_present:
        # A Groq key with no explicit choice means the coach is really Groq.
        settings = ProviderSettings(
            provider_mode="openai_compatible",
            base_url=settings.base_url or GROQ_BASE_URL,
            model=settings.model or GROQ_MODEL,
            timeout_s=settings.timeout_s,
        )
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
    # With a Groq key present and no explicit provider chosen, use Groq rather
    # than the offline rule engine: the coach becomes a real model.
    source = os.environ if env is None else env
    groq_present = bool(str(source.get("GROQ_API_KEY", "") or "").strip())
    if settings.provider_mode == "mock":
        if not groq_present:
            return MockCoachProvider()
        settings = ProviderSettings(
            provider_mode="openai_compatible",
            base_url=settings.base_url or GROQ_BASE_URL,
            model=settings.model or GROQ_MODEL,
            timeout_s=settings.timeout_s,
        )
    elif not settings.base_url and groq_present:
        settings = ProviderSettings(
            provider_mode=settings.provider_mode,
            base_url=GROQ_BASE_URL,
            model=settings.model or GROQ_MODEL,
            timeout_s=settings.timeout_s,
        )
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
