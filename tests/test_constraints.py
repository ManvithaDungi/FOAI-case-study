"""Hard-constraint checks and the independent ConstraintChecker (constraints.py)."""

from __future__ import annotations

import pytest

from constraints import (ConstraintChecker, check_biostatistician, check_ethics, check_patient_advocate,
                         check_sponsor)
from models import BIOSTATISTICIAN, ETHICS, PATIENT_ADVOCATE, SPONSOR
from scenarios import load_scenario


@pytest.fixture
def s():
    return load_scenario("baseline")


def c(s, agent):
    return s.private_states[agent].private_constraints


def test_initial_draft_breaks_sponsor_ethics_and_advocate_limits(s):
    audit = ConstraintChecker({k: v.private_constraints for k, v in s.private_states.items()}, s.context).check_all(s.protocol)
    agents = {v["agent"] for v in audit["violations"]}
    assert not audit["valid"]
    assert {"Sponsor", "Ethics Committee", "Patient Advocate"} <= agents


def test_audit_entries_have_agent_constraint_actual(s):
    audit = ConstraintChecker({k: v.private_constraints for k, v in s.private_states.items()}, s.context).check_all(s.protocol)
    assert all(set(v) == {"agent", "constraint", "actual"} for v in audit["violations"])


def test_sponsor_flags_cost_and_sample_size(s):
    fields = {v.field for v in check_sponsor(s.protocol, c(s, SPONSOR), s.context)}
    assert {"estimated_cost", "sample_size"} <= fields


def test_biostatistician_flags_low_power_and_wrong_alpha(s):
    weak = s.protocol.with_changes({"sample_size": 60, "alpha": 0.1})
    constraints = {v.constraint.split()[0] for v in check_biostatistician(weak, c(s, BIOSTATISTICIAN), s.context)}
    assert {"power", "alpha"} <= constraints


def test_biomarker_endpoint_needs_a_sampling_procedure(s):
    p = s.protocol.with_changes({"primary_endpoint": "continuous_biomarker", "invasive_procedures": 0})
    assert any(v.field == "invasive_procedures" for v in check_biostatistician(p, c(s, BIOSTATISTICIAN), s.context))


def test_ethics_flags_dose_ae_reporting_and_missing_exclusions(s):
    fields = {v.field for v in check_ethics(s.protocol, c(s, ETHICS), s.context)}
    assert {"dosage", "adverse_event_reporting", "exclusion_criteria"} <= fields


def test_ethics_allows_few_visits_only_with_remote_monitoring(s):
    p = s.protocol.with_changes({"hospital_visits": 4, "remote_monitoring": False})
    assert any(v.field == "remote_monitoring" for v in check_ethics(p, c(s, ETHICS), s.context))
    p = p.with_changes({"remote_monitoring": True})
    assert not any(v.field == "remote_monitoring" for v in check_ethics(p, c(s, ETHICS), s.context))


def test_advocate_flags_burden_and_narrow_eligibility(s):
    p = s.protocol.with_changes({"exclusion_criteria": ["a", "b", "c", "d", "e"]})
    fields = {v.field for v in check_patient_advocate(p, c(s, PATIENT_ADVOCATE), s.context)}
    assert {"hospital_visits", "invasive_procedures", "exclusion_criteria"} <= fields


def test_public_messages_never_contain_thresholds(s):
    p = s.protocol.with_changes({"sample_size": 60, "dosage": 150.0})
    for fn, agent in [(check_sponsor, SPONSOR), (check_biostatistician, BIOSTATISTICIAN),
                      (check_ethics, ETHICS), (check_patient_advocate, PATIENT_ADVOCATE)]:
        for v in fn(p, c(s, agent), s.context):
            assert not any(ch.isdigit() for ch in v.public_message), v.public_message


def test_checker_role_methods_match_check_all(s):
    checker = ConstraintChecker({k: v.private_constraints for k, v in s.private_states.items()}, s.context)
    total = sum(len(f(s.protocol)) for f in (checker.check_sponsor, checker.check_biostatistician,
                                             checker.check_ethics, checker.check_patient_advocate))
    assert total == len(checker.check_all(s.protocol)["violations"])
