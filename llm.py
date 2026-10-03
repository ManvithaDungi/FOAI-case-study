"""Tiny OpenAI-compatible chat client built on urllib (no SDK dependency)."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Protocol as TypingProtocol

from config import Settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised for transport errors or unusable responses."""


class ChatClient(TypingProtocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


class OpenAICompatibleClient:
    """Calls POST {base_url}/chat/completions and returns the message text."""

    def __init__(self, settings: Settings) -> None:
        if not settings.llm_available:
            raise LLMError("No API key configured.")
        self._settings = settings

    def complete(self, messages: list[dict[str, str]]) -> str:
        body = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": self._settings.temperature,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self._settings.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._settings.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._settings.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {payload!r:.200}") from exc


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating ```json fences."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model output.")
    data = json.loads(cleaned[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Model output is not a JSON object.")
    return data


def build_client(settings: Settings, use_llm: bool) -> ChatClient | None:
    """Return an LLM client when requested and configured, otherwise None (mock mode)."""
    if not use_llm:
        return None
    if not settings.llm_available:
        log.warning("--llm requested but OPENAI_API_KEY is not set; falling back to MOCK mode.")
        return None
    return OpenAICompatibleClient(settings)
