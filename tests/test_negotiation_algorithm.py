"""Negotiation algorithm (negotiation.py): ordering, authority, splitting, learning, termination."""

from __future__ import annotations

import json

import pytest

from agents import create_agents
from environment import ClinicalTrialEnvironment
from models import BIOSTATISTICIAN, ETHICS, PATIENT_ADVOCATE, SPONSOR, NegotiationStatus, Proposal, ProposalStatus
from negotiation import PROCESSING_ORDER, NegotiationEngine
from scenarios import load_scenario


def setup(key="baseline", llm=None, max_rounds=10):
    s = load_scenario(key)
    env = ClinicalTrialEnvironment(s)
    agents = create_agents(env, llm)
    return s, env, agents, NegotiationEngine(env, agents, max_rounds=max_rounds)


def test_processing_order_puts_irb_first():
    assert PROCESSING_ORDER[0] == ETHICS and set(PROCESSING_ORDER) == {SPONSOR, BIOSTATISTICIAN, ETHICS, PATIENT_ADVOCATE}


def test_max_rounds_must_be_positive():
    s = load_scenario("baseline")
    env = ClinicalTrialEnvironment(s)
    with pytest.raises(ValueError):
        NegotiationEngine(env, create_agents(env), max_rounds=0)


def test_irb_safety_change_overrides_objections():
    _, env, _, engine = setup()
    env.start_round(1)
    p = Proposal(ETHICS, {"dosage": 75.0}, "safety", 1)
    candidate = engine.process_proposal(p, env.current_protocol.copy())
    assert p.status == ProposalStatus.ACCEPTED and candidate.dosage == 75.0


def test_underpowered_sample_cut_is_blocked_by_biostatistician():
    _, env, _, engine = setup()
    env.start_round(1)
    p = Proposal(SPONSOR, {"sample_size": 60}, "cost", 1)
    candidate = engine.process_proposal(p, env.current_protocol.copy())
    assert p.status == ProposalStatus.REJECTED and candidate.sample_size == 320
    assert any("underpowered" in o for o in p.objections)


def test_blocked_multi_field_proposal_is_split_field_by_field():
    _, env, _, engine = setup()
    env.start_round(1)
    p = Proposal(SPONSOR, {"sample_size": 60, "dosage_arms": 1}, "cost", 1)
    engine.process_proposal(p, env.current_protocol.copy())
    assert p.status == ProposalStatus.PARTIALLY_ACCEPTED
    assert "dosage_arms" in p.accepted_changes and "sample_size" in p.rejected_changes


def test_advocate_objection_is_advisory_only():
    _, env, agents, _ = setup()
    assert agents[PATIENT_ADVOCATE].can_block is False
    assert agents[SPONSOR].can_block and agents[BIOSTATISTICIAN].can_block


def test_baseline_walkthrough_round_one():
    _, _, _, engine = setup()
    s = load_scenario("baseline")
    r1 = engine.run(s).rounds[0]
    by_agent = {p.agent: p for p in r1.proposals}
    assert by_agent[ETHICS].accepted_changes["dosage"] == 75.0
    assert "sample_size" in by_agent[SPONSOR].rejected_changes


def test_sponsor_learns_the_hidden_power_bar_from_objections():
    s, _, agents, engine = setup()
    engine.run(s)
    learned = agents[SPONSOR]._learned_min_power
    assert 0.6 < learned < 0.8  # inferred from the blocked cut, never read from private state


def test_mock_mode_is_deterministic():
    a = setup()[3].run(load_scenario("baseline"))
    b = setup()[3].run(load_scenario("baseline"))
    assert a.final_protocol.to_dict() == b.final_protocol.to_dict()
    assert a.metrics["rounds"] == b.metrics["rounds"]


def test_each_accepted_round_creates_a_new_version():
    s, env, _, engine = setup()
    result = engine.run(s)
    assert result.final_protocol.version == len(env.protocol_versions)


class StuckLLM:
    """Sponsor keeps proposing a blocked cut; Advocate repeats values already in place; others approve."""

    def complete(self, messages):
        prompt = messages[0]["content"].upper()
        if "SPONSOR" in prompt:
            return json.dumps({"decision": "COUNTER_PROPOSE", "reason": "Cost.", "proposed_changes": {"sample_size": 60}})
        if "PATIENT ADVOCATE" in prompt:
            return json.dumps({"decision": "COUNTER_PROPOSE", "reason": "Burden.",
                               "proposed_changes": {"hospital_visits": 12}})
        return json.dumps({"decision": "APPROVE", "reason": "Fine."})


def test_no_progress_for_two_rounds_is_a_deadlock():
    s, _, _, engine = setup(llm=StuckLLM())
    result = engine.run(s)
    assert result.status == NegotiationStatus.DEADLOCK
    assert result.metrics["rounds"] < 10 and result.unresolved_conflicts


def test_repeating_current_values_is_not_a_proposal():
    s, _, _, engine = setup(llm=StuckLLM(), max_rounds=1)
    rnd = engine.run(s).rounds[0]
    assert PATIENT_ADVOCATE not in {p.agent for p in rnd.proposals}  # 12 visits is already the value
