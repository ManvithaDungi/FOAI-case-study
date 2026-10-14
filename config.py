"""Configuration: reads environment variables and an optional .env file (no extra dependencies)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DEFAULT_MAX_ROUNDS = 10


def load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, '#' comments, optional quotes."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    base_url: str
    model: str
    temperature: float
    timeout_seconds: int
    min_interval_seconds: float = 0.0  # pause between LLM calls (free tiers limit requests per minute)
    max_retries: int = 4  # extra attempts on HTTP 429 / 5xx, with backoff

    @property
    def llm_available(self) -> bool:
        return bool(self.api_key) and self.api_key != "your_api_key_here"


def load_settings(env_file: Path | None = None) -> Settings:
    """Environment variables win over values in the .env file."""
    file_values = load_dotenv(env_file or PROJECT_ROOT / ".env")

    def get(key: str, default: str | None = None) -> str | None:
        return os.environ.get(key) or file_values.get(key) or default

    return Settings(
        api_key=get("OPENAI_API_KEY"),
        base_url=(get("OPENAI_BASE_URL", "https://api.openai.com/v1") or "").rstrip("/"),
        model=get("MODEL", "gpt-4o-mini") or "gpt-4o-mini",
        temperature=float(get("LLM_TEMPERATURE", "0.2") or 0.2),
        timeout_seconds=int(get("LLM_TIMEOUT_SECONDS", "60") or 60),
        min_interval_seconds=float(get("LLM_MIN_INTERVAL_SECONDS", "0") or 0),
        max_retries=int(get("LLM_MAX_RETRIES", "4") or 4),
    )
