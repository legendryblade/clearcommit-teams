"""OpenAI-compatible chat-completions adapter.

Uses only the standard library. The API key is read from the process
environment at call time and is never persisted, logged, or returned.
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..errors import (
    AppError,
    ProviderAuthError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .base import AssistantRequest, CoachRequest, ProviderDescriptor
from .prompts import (
    ASSISTANT_SYSTEM,
    COACH_SYSTEM,
    build_assistant_user_prompt,
    build_coach_user_prompt,
)

_RETRY_STATUS = {429, 502, 503, 504}


class HttpTransport(Protocol):
    def post_json(self, url: str, headers: dict, payload: dict, timeout_s: float) -> tuple[int, str]:
        ...


class UrllibTransport:
    def post_json(self, url: str, headers: dict, payload: dict, timeout_s: float) -> tuple[int, str]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(url, data=data, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout_s) as response:
                return int(response.status), response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return int(exc.code), body
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderTimeoutError(
                "The provider did not respond before the timeout. Try again or increase the timeout."
            ) from exc
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise ProviderTimeoutError(
                    "The provider did not respond before the timeout. Try again or increase the timeout."
                ) from exc
            raise ProviderUnavailableError(
                "Could not reach the configured provider. Check the network and base URL."
            ) from exc
        except OSError as exc:
            raise ProviderUnavailableError(
                "Could not reach the configured provider. Check the network and base URL."
            ) from exc


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: str
    timeout_s: float = 25.0
    retry_delay_s: float = 0.8
    temperature: float = 0.2

    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"


class OpenAICompatibleProvider:
    def __init__(self, config: OpenAICompatibleConfig, transport: HttpTransport | None = None) -> None:
        self.config = config
        self._transport = transport or UrllibTransport()
        host = urlparse(config.base_url).netloc or "configured endpoint"
        self.descriptor = ProviderDescriptor(
            mode="openai_compatible",
            name=f"OpenAI-compatible · {host}",
            model=config.model,
        )

    def _chat(self, system: str, user: str, *, max_tokens: int) -> str:
        if not self.config.api_key:
            raise ProviderNotConfiguredError(
                "No provider API key is available. Set CLEARCOMMIT_TEAMS_API_KEY and restart."
            )
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
            "max_tokens": max_tokens,
        }
        status = 0
        body = ""
        for attempt in range(2):
            status, body = self._transport.post_json(
                self.config.endpoint(), headers, payload, self.config.timeout_s
            )
            if status in _RETRY_STATUS and attempt == 0:
                if self.config.retry_delay_s:
                    time.sleep(self.config.retry_delay_s)
                continue
            break

        if status == 401 or status == 403:
            raise ProviderAuthError(
                "The provider rejected the API key. Check CLEARCOMMIT_TEAMS_API_KEY."
            )
        if status == 429:
            raise ProviderRateLimitError(
                "The provider is rate limiting requests. Wait a moment and retry."
            )
        if status in (404, 400):
            raise ProviderError(
                "The provider rejected the request. Check the base URL and model name.",
                detail={"status": status},
            )
        if status >= 500:
            raise ProviderUnavailableError(
                "The provider is unavailable right now. Try again shortly.",
                detail={"status": status},
            )
        if status != 200:
            raise ProviderError(
                "The provider returned an unexpected response.",
                detail={"status": status},
            )
        try:
            data = json.loads(body)
        except (TypeError, ValueError) as exc:
            raise ProviderUnavailableError(
                "The provider returned a response that was not valid JSON."
            ) from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailableError(
                "The provider response did not contain a chat completion."
            ) from exc
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
            content = "".join(parts)
        if not isinstance(content, str) or not content.strip():
            raise ProviderUnavailableError("The provider returned an empty response.")
        return content.strip()

    def generate_coaching(self, request: CoachRequest) -> str:
        return self._chat(
            COACH_SYSTEM,
            build_coach_user_prompt(request),
            max_tokens=2200,
        )

    def generate_answer(self, request: AssistantRequest) -> str:
        return self._chat(
            ASSISTANT_SYSTEM,
            build_assistant_user_prompt(request),
            max_tokens=900,
        )

    def test_connection(self) -> dict:
        try:
            content = self._chat(
                "You are a connectivity check. Do not add commentary.",
                'Return exactly {"ok":true} and nothing else.',
                max_tokens=24,
            )
        except AppError as exc:
            return {
                "ok": False,
                "message": exc.message,
                "code": exc.code,
                "network": True,
            }
        return {
            "ok": True,
            "message": "The configured provider responded.",
            "network": True,
            "model": self.config.model,
            "response_preview": content[:120],
        }
