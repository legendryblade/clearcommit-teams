"""Provider adapters for ClearCommit Teams."""

from .base import AssistantRequest, CoachRequest, EvidenceItem, ProviderDescriptor
from .mock import MockCoachProvider
from .openai_compat import OpenAICompatibleConfig, OpenAICompatibleProvider, UrllibTransport
from .registry import (
    API_KEY_ENV,
    ProviderSettings,
    build_provider,
    provider_status,
)

__all__ = [
    "API_KEY_ENV",
    "AssistantRequest",
    "CoachRequest",
    "EvidenceItem",
    "MockCoachProvider",
    "OpenAICompatibleConfig",
    "OpenAICompatibleProvider",
    "ProviderDescriptor",
    "ProviderSettings",
    "UrllibTransport",
    "build_provider",
    "provider_status",
]
