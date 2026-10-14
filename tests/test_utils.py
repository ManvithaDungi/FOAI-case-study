"""Utility code: config loading, LLM client, JSON parsing, logging, redaction (config/llm/logger/agents)."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from email.message import Message

import pytest

import llm
from agents import create_agents
from config import Settings, load_dotenv
from environment import ClinicalTrialEnvironment
from logger import EventLogger, format_changes
from models import ETHICS
from scenarios import load_scenario


def test_load_dotenv_parses_comments_and_quotes(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nMODEL='gemini-test'\nOPENAI_API_KEY=\"abc\"\nBROKEN LINE\n", encoding="utf-8")
    assert load_dotenv(env) == {"MODEL": "gemini-test", "OPENAI_API_KEY": "abc"}
    assert load_dotenv(tmp_path / "missing.env") == {}


def settings(**kw):
    base = dict(api_key="k", base_url="http://x", model="m", temperature=0.2, timeout_seconds=5,
                min_interval_seconds=0, max_retries=2)
    base.update(kw)
    return Settings(**base)


def test_placeholder_key_means_no_llm():
    assert not settings(api_key="your_api_key_here").llm_available
    assert not settings(api_key=None).llm_available and settings().llm_available


def test_build_client_returns_none_in_mock_mode():
    assert llm.build_client(settings(), use_llm=False) is None
    assert llm.build_client(settings(api_key=None), use_llm=True) is None


def test_extract_json_handles_code_fences_and_errors():
    assert llm.extract_json('```json\n{"decision": "APPROVE"}\n```') == {"decision": "APPROVE"}
    assert llm.extract_json('Sure! {"a": 1} hope that helps') == {"a": 1}
    with pytest.raises(ValueError):
        llm.extract_json("no json here")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _fake_urlopen(codes):
    calls = []

    def fake(request, timeout=0):
        calls.append(request)
        if len(calls) <= len(codes):
            headers = Message()
            headers["Retry-After"] = "0"
            raise urllib.error.HTTPError(request.full_url, codes[len(calls) - 1], "err", headers, None)
        return _Resp(json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode())
    return fake, calls


def test_llm_client_retries_on_rate_limit_then_succeeds(monkeypatch):
    fake, calls = _fake_urlopen([503, 429])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert llm.OpenAICompatibleClient(settings()).complete([{"role": "user", "content": "hi"}]) == "{}"
    assert len(calls) == 3 and calls[0].full_url == "http://x/chat/completions"


def test_llm_client_does_not_retry_bad_requests(monkeypatch):
    fake, calls = _fake_urlopen([400])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(llm.LLMError):
        llm.OpenAICompatibleClient(settings()).complete([])
    assert len(calls) == 1


def test_format_changes_handles_numbers_lists_and_text_requests():
    out = format_changes({"budget": 9_500_000.0, "power": 0.84731, "exclusion_criteria": ["a", "b"],
                          "inclusion_criteria": [], "estimated_cost": "decrease"})
    assert "budget=$9.50M" in out and "power=0.847" in out and "exclusion_criteria=a, b" in out
    assert "inclusion_criteria=(none)" in out and "estimated_cost=decrease" in out


def test_event_logger_writes_one_json_line_per_event(tmp_path):
    log = EventLogger()
    log.log_event(1, "Sponsor", "REVIEW", "reason", {"sample_size": 180}, "COUNTER_PROPOSE")
    log.log_event(1, "Biostatistician", "OBJECTION")
    path = tmp_path / "out" / "events.jsonl"
    log.save(path)
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2 and lines[0]["proposal"] == {"sample_size": 180} and lines[1]["round"] == 1


def test_sanitize_redacts_private_thresholds():
    env = ClinicalTrialEnvironment(load_scenario("baseline"))
    irb = create_agents(env)[ETHICS]
    text = irb.sanitize("The dose must stay under 75 mg; we need 8 visits.")
    assert "75" not in text and "[private]" in text
