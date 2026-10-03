"""Tests for the multi-agent clinical trial negotiation (run with: pytest -q)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from agents import EthicsAgent, PatientAdvocateAgent, create_agents
from config import load_settings
from environment import ClinicalTrialEnvironment, PrivateStateAccessError
from llm import build_client
from main import run_multi_agent
from models import (BIOSTATISTICIAN, ETHICS, PATIENT_ADVOCATE, SPONSOR, Decision, NegotiationStatus,
                    Proposal, ProposalStatus)
from negotiation import NegotiationEngine
from scenarios import SCENARIOS, load_scenario

PRIVATE_KEYS = {
    SPONSOR: ["max_budget_usd", "max_sample_size", "max_duration_months"],
    BIOSTATISTICIAN: ["min_power", "required_alpha"],
    ETHICS: ["max_dosage_mg", "min_visits_without_remote", "required_exclusions"],
    PATIENT_ADVOCATE: ["max_hospital_visits", "max_exclusion_criteria"],
}


def _setup(key: str = "baseline", max_rounds: int = 10, llm_client=None):
    scenario = load_scenario(key)
    env = ClinicalTrialEnvironment(scenario)
    agents = create_agents(env, llm_client)
    return scenario, env, agents, NegotiationEngine(env, agents, max_rounds=max_rounds)


# 1 ---------------------------------------------------------------------
def test_sponsor_cannot_modify_unauthorized_fields():
    _, env, _, engine = _setup()
    env.start_round(1)
    proposal = Proposal(SPONSOR, {"dosage": 150.0, "hospital_visits": 2, "dosage_arms": 1}, "cut costs", 1)
    candidate = engine.process_proposal(proposal, env.current_protocol.copy())
    assert "dosage" in proposal.rejected_changes and "hospital_visits" in proposal.rejected_changes
    assert candidate.dosage == env.current_protocol.dosage
    assert candidate.hospital_visits == env.current_protocol.hospital_visits
    assert any("not authorised" in o for o in proposal.objections)
    assert proposal.status == ProposalStatus.PARTIALLY_ACCEPTED  # the authorised field went through


# 2 ---------------------------------------------------------------------
def test_private_constraints_not_in_other_agents_context():
    _, env, agents, _ = _setup()
    env.start_round(1)
    shared = env.get_shared_state()
    for owner, agent in agents.items():
        prompt = json.dumps(agent.build_llm_messages(shared.protocol, shared))
        for key in PRIVATE_KEYS[owner]:
            assert key in prompt, f"{owner} should see its own {key}"
        for other, keys in PRIVATE_KEYS.items():
            if other != owner:
                for key in keys:
                    assert key not in prompt, f"{key} of {other} leaked to {owner}"
    public = json.dumps(shared.to_public_dict(), default=str)
    assert not any(k in public for keys in PRIVATE_KEYS.values() for k in keys)


def test_environment_refuses_cross_agent_private_access():
    _, env, _, _ = _setup()
    assert env.get_private_state(ETHICS, requester_id=ETHICS).private_constraints["max_dosage_mg"] == 75.0
    try:
        env.get_private_state(ETHICS, requester_id=SPONSOR)
    except PrivateStateAccessError:
        return
    raise AssertionError("Sponsor was able to read the Ethics Committee's private state")


def test_public_transcript_does_not_reveal_private_thresholds():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_multi_agent("baseline", output_dir=Path(tmp))
    board = " ".join(m.content for m in result.transcript)
    for leaked in ("75 mg", "0.80", "80%", "$15", "15,000,000", "220"):
        assert leaked not in board


# 3 ---------------------------------------------------------------------
def test_checker_detects_invalid_sample_size():
    _, env, _, _ = _setup()
    protocol = env.preview(env.current_protocol, {"sample_size": 300})
    violations = env.constraint_checker.check_sponsor(protocol)
    assert any(v.constraint.startswith("sample_size <=") for v in violations)
    report = env.constraint_checker.check_all(protocol)
    assert report["valid"] is False
    assert any(v["agent"] == "Sponsor" and v["actual"] == 300 for v in report["violations"])


# 4 ---------------------------------------------------------------------
def test_checker_detects_power_below_80_percent():
    _, env, _, _ = _setup()
    protocol = env.preview(env.current_protocol, {"sample_size": 100})
    assert protocol.power < 0.80
    report = env.constraint_checker.check_all(protocol)
    assert any(v["agent"] == "Biostatistician" and v["constraint"].startswith("power") for v in report["violations"])


# 5 ---------------------------------------------------------------------
def test_ethics_agent_rejects_unsafe_dosage():
    _, env, agents, _ = _setup()
    env.start_round(1)
    ethics: EthicsAgent = agents[ETHICS]  # type: ignore[assignment]
    unsafe = env.preview(env.current_protocol, {"dosage": 150.0})
    decision = ethics.review_protocol(unsafe, env.get_shared_state())
    assert decision.decision != Decision.APPROVE
    assert decision.proposed_changes["dosage"] < 150.0
    assert "75" not in decision.reason  # threshold stays hidden
    safe = env.preview(env.current_protocol, {"dosage": 50.0})
    review = ethics.evaluate_proposal(safe, unsafe, Proposal(SPONSOR, {"dosage": 150.0}, ""), env.context)
    assert review.accept is False and review.can_block is True


# 6 ---------------------------------------------------------------------
def test_patient_advocate_rejects_excessive_hospital_visits():
    _, env, agents, _ = _setup()
    env.start_round(1)
    advocate: PatientAdvocateAgent = agents[PATIENT_ADVOCATE]  # type: ignore[assignment]
    protocol = env.preview(env.current_protocol, {"hospital_visits": 20})
    decision = advocate.review_protocol(protocol, env.get_shared_state())
    assert decision.decision != Decision.APPROVE
    assert decision.proposed_changes["hospital_visits"] < 20
    assert any(v.field == "hospital_visits" for v in env.constraint_checker.check_patient_advocate(protocol))


# 7 ---------------------------------------------------------------------
def test_negotiation_stops_when_all_agents_approve():
    with tempfile.TemporaryDirectory() as tmp:
        agreed = run_multi_agent("baseline", output_dir=Path(tmp)).final_protocol
    scenario = load_scenario("baseline")
    scenario.protocol = agreed
    env = ClinicalTrialEnvironment(scenario)
    result = NegotiationEngine(env, create_agents(env), max_rounds=10).run(scenario)
    assert result.status == NegotiationStatus.CONSENSUS
    assert result.metrics["rounds"] == 1
    assert result.metrics["proposals_total"] == 0


def test_baseline_reaches_consensus_with_zero_violations():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_multi_agent("baseline", output_dir=Path(tmp))
        assert (Path(tmp) / "baseline.json").exists() and (Path(tmp) / "baseline_events.jsonl").exists()
    assert result.status == NegotiationStatus.CONSENSUS
    assert result.metrics["constraint_violations"] == 0
    assert result.final_protocol.power >= 0.80 and result.final_protocol.dosage <= 75


# 8 ---------------------------------------------------------------------
def test_negotiation_stops_after_max_rounds():
    scenario = load_scenario("baseline")
    # Impossible: the sponsor will never fund enough patients for adequate power.
    scenario.private_states[SPONSOR].private_constraints["max_sample_size"] = 40
    scenario.private_states[SPONSOR].preferences["target_sample_size"] = 40
    for limit in (1, 3):
        env = ClinicalTrialEnvironment(scenario)
        result = NegotiationEngine(env, create_agents(env), max_rounds=limit).run(scenario)
        assert result.status != NegotiationStatus.CONSENSUS
        assert result.metrics["rounds"] <= limit
        assert result.unresolved_conflicts


# 9 ---------------------------------------------------------------------
def test_scenario_loading():
    assert len(SCENARIOS) == 8  # baseline + seven test scenarios
    for key in SCENARIOS:
        scenario = load_scenario(key)
        assert scenario.key == key and set(scenario.private_states) == set(PRIVATE_KEYS)
    assert load_scenario("budget_reduction").private_states[SPONSOR].private_constraints["max_budget_usd"] == 9e6
    assert load_scenario("pediatric").private_states[ETHICS].private_constraints["required_inclusions"]
    try:
        load_scenario("does_not_exist")
    except KeyError:
        return
    raise AssertionError("unknown scenario should raise KeyError")


def test_every_scenario_terminates():
    with tempfile.TemporaryDirectory() as tmp:
        for key in SCENARIOS:
            result = run_multi_agent(key, output_dir=Path(tmp))
            assert result.metrics["rounds"] <= 10


# 10 --------------------------------------------------------------------
def test_mock_mode_works_without_api_key():
    saved = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings(Path(tmp) / "missing.env")
            assert not settings.llm_available
            client = build_client(settings, use_llm=True)
            assert client is None
            result = run_multi_agent("pandemic", client, output_dir=Path(tmp))
        assert result.mode == "mock"
        assert all(d.source == "mock" for r in result.rounds for d in r.decisions)
    finally:
        if saved is not None:
            os.environ["OPENAI_API_KEY"] = saved


# LLM-mode plumbing (with a fake client, no network) ----------------------
class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        return self.replies.pop(0) if self.replies else "not json"


def test_llm_retry_then_fallback_to_mock():
    _, env, _, _ = _setup()
    env.start_round(1)
    client = FakeClient(["garbage", "{still not json"])
    agents = create_agents(env, client)
    decision = agents[ETHICS].review_protocol(env.current_protocol.copy(), env.get_shared_state())
    assert client.calls == 2  # one retry
    assert decision.source == "llm-fallback" and decision.proposed_changes["dosage"] <= 75


def test_llm_valid_json_is_used_and_sanitized():
    _, env, _, _ = _setup()
    env.start_round(1)
    reply = json.dumps({"decision": "COUNTER_PROPOSE", "reason": "Dose must not exceed 75 mg.",
                        "proposed_changes": {"dosage": 50}, "requests": {"remote_monitoring": "enable"}})
    agents = create_agents(env, FakeClient(["oops", reply]))
    decision = agents[ETHICS].review_protocol(env.current_protocol.copy(), env.get_shared_state())
    assert decision.source == "llm" and decision.proposed_changes == {"dosage": 50.0}
    assert "75" not in decision.reason and "[private]" in decision.reason


def test_llm_cannot_approve_when_hard_constraints_fail():
    _, env, _, _ = _setup()
    env.start_round(1)
    agents = create_agents(env, FakeClient([json.dumps({"decision": "APPROVE", "reason": "looks fine"})]))
    decision = agents[ETHICS].review_protocol(env.current_protocol.copy(), env.get_shared_state())
    assert decision.decision != Decision.APPROVE and decision.source == "llm-guard"


def test_llm_unauthorized_field_is_rejected_by_validation():
    _, env, _, _ = _setup()
    env.start_round(1)
    bad = json.dumps({"decision": "COUNTER_PROPOSE", "reason": "cheaper", "proposed_changes": {"dosage": 200}})
    agents = create_agents(env, FakeClient([bad, bad]))
    decision = agents[SPONSOR].review_protocol(env.current_protocol.copy(), env.get_shared_state())
    assert "dosage" not in decision.proposed_changes and decision.source == "llm-fallback"
