"""Scenario setup and end-to-end outcomes for all 8 test scenarios (scenarios.py)."""

from __future__ import annotations

import pytest

from agents import create_agents
from environment import ClinicalTrialEnvironment
from models import BIOSTATISTICIAN, ETHICS, PATIENT_ADVOCATE, SPONSOR, NegotiationStatus
from negotiation import NegotiationEngine
from scenarios import SCENARIOS, load_scenario
from single_agent import SingleAgentPlanner

# scenario -> expected rounds to consensus in mock mode
EXPECTED_ROUNDS = {"baseline": 4, "budget_reduction": 5, "high_risk_drug": 5, "rare_disease": 5,
                   "pediatric": 4, "pandemic": 4, "multi_country": 4, "unexpected_interim": 3}


def run(key):
    s = load_scenario(key)
    env = ClinicalTrialEnvironment(s)
    return s, NegotiationEngine(env, create_agents(env)).run(s)


def test_every_scenario_is_listed():
    assert set(SCENARIOS) == set(EXPECTED_ROUNDS)


def test_load_scenario_returns_fresh_copies():
    a, b = load_scenario("baseline"), load_scenario("baseline")
    a.private_states[SPONSOR].private_constraints["max_budget_usd"] = 1
    assert b.private_states[SPONSOR].private_constraints["max_budget_usd"] == 15_000_000.0


@pytest.mark.parametrize("key", list(EXPECTED_ROUNDS))
def test_scenario_reaches_consensus_with_zero_violations(key):
    _, result = run(key)
    assert result.status == NegotiationStatus.CONSENSUS
    assert result.metrics["rounds"] == EXPECTED_ROUNDS[key]
    assert result.metrics["constraint_violations"] == 0 and result.constraint_check["valid"]


@pytest.mark.parametrize("key", list(EXPECTED_ROUNDS))
def test_single_agent_baseline_breaks_constraints(key):
    assert SingleAgentPlanner(load_scenario(key)).plan()["constraint_violations"] > 0


def test_budget_reduction_stays_under_9m():
    s, r = run("budget_reduction")
    assert s.private_states[SPONSOR].private_constraints["max_budget_usd"] == 9e6
    assert r.final_protocol.estimated_cost <= 9e6


def test_high_risk_drug_keeps_strict_safety():
    _, r = run("high_risk_drug")
    p = r.final_protocol
    assert p.dosage <= 50 and p.safety_monitoring_frequency == "weekly"
    assert p.adverse_event_reporting == "expedited_24h" and "cardiac_arrhythmia" in p.exclusion_criteria
    assert p.trial_duration_months <= 14


def test_rare_disease_fits_the_patient_pool():
    s, r = run("rare_disease")
    assert s.context.recruitment["eligible_population"] == 260
    assert r.final_protocol.sample_size <= 260
    assert len(r.final_protocol.exclusion_criteria) <= 3


def test_pediatric_has_consent_low_dose_and_one_procedure():
    _, r = run("pediatric")
    p = r.final_protocol
    assert {"parental_consent", "child_assent"} <= set(p.inclusion_criteria)
    assert p.dosage <= 40 and p.invasive_procedures <= 1 and p.remote_monitoring


def test_pandemic_meets_deadline_without_relaxing_safety():
    _, r = run("pandemic")
    p = r.final_protocol
    assert p.trial_duration_months <= 9
    assert p.safety_monitoring_frequency == "weekly" and p.adverse_event_reporting == "expedited_24h"


def test_multi_country_applies_strictest_rules():
    _, r = run("multi_country")
    assert "participation_in_other_trial" in r.final_protocol.exclusion_criteria
    assert r.final_protocol.safety_monitoring_frequency in ("biweekly", "weekly")


def test_unexpected_interim_keeps_locked_design_fields():
    s, r = run("unexpected_interim")
    p = r.final_protocol
    locked = s.private_states[BIOSTATISTICIAN].private_constraints["locked_fields"]
    assert all(getattr(p, f) == v for f, v in locked.items())
    assert p.dosage <= 50 and p.sample_size >= 120


def test_scenarios_only_change_their_own_settings():
    base, high = load_scenario("baseline"), load_scenario("high_risk_drug")
    assert high.private_states[PATIENT_ADVOCATE].private_constraints == base.private_states[PATIENT_ADVOCATE].private_constraints
    assert high.private_states[ETHICS].private_constraints["max_dosage_mg"] < base.private_states[ETHICS].private_constraints["max_dosage_mg"]
