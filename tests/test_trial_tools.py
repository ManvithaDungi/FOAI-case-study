"""Public calculator functions (trial_tools.py): power, sample size, cost, recruitment."""

from __future__ import annotations

import pytest

from scenarios import load_scenario
from trial_tools import (calculate_power, eligibility_factor, estimate_cost, hospitals_needed, level_index,
                         max_enrollable, normal_cdf, projected_enrollment_months, public_tool_report,
                         refresh_derived, required_sample_size, z_quantile)


@pytest.fixture
def base():
    s = load_scenario("baseline")
    return s.protocol, s.context


def test_normal_cdf_and_z_quantile_are_inverses():
    assert normal_cdf(0) == pytest.approx(0.5)
    assert z_quantile(0.975) == pytest.approx(1.96, abs=0.01)
    assert normal_cdf(z_quantile(0.8)) == pytest.approx(0.8, abs=1e-6)


def test_power_rises_with_sample_size(base):
    p, ctx = base
    assert calculate_power(p.with_changes({"sample_size": 400}), ctx) > calculate_power(p.with_changes({"sample_size": 150}), ctx)


def test_power_rises_with_more_sensitive_endpoint_and_stratification(base):
    p, ctx = base
    plain = calculate_power(p, ctx)
    assert calculate_power(p.with_changes({"primary_endpoint": "continuous_biomarker"}), ctx) > plain
    assert calculate_power(p.with_changes({"randomization_scheme": "stratified_block"}), ctx) > plain


def test_power_falls_with_lower_dose(base):
    p, ctx = base
    assert calculate_power(p.with_changes({"dosage": 50.0}), ctx) < calculate_power(p, ctx)


def test_power_is_zero_for_degenerate_designs(base):
    p, ctx = base
    assert calculate_power(p.with_changes({"sample_size": 2}), ctx) == 0.0


def test_required_sample_size_reaches_target_power(base):
    p, ctx = base
    n = required_sample_size(p, ctx, 0.8)
    assert n % 5 == 0
    assert calculate_power(p.with_changes({"sample_size": n}), ctx) >= 0.8


def test_known_baseline_values(base):
    p, ctx = base
    assert calculate_power(p.with_changes({"dosage": 75.0, "dosage_arms": 1, "sample_size": 180}), ctx) == pytest.approx(0.6428, abs=1e-3)
    assert estimate_cost(p, ctx) == pytest.approx(26_000_000.0)


def test_cost_rises_with_visits_and_procedures(base):
    p, ctx = base
    assert estimate_cost(p.with_changes({"hospital_visits": 4}), ctx) < estimate_cost(p, ctx)
    assert estimate_cost(p.with_changes({"invasive_procedures": 1}), ctx) < estimate_cost(p, ctx)
    assert estimate_cost(p.with_changes({"remote_monitoring": True}), ctx) > estimate_cost(p, ctx)


def test_eligibility_factor_is_bounded_and_drops_with_exclusions(base):
    p, ctx = base
    wide = eligibility_factor(p.with_changes({"exclusion_criteria": [], "inclusion_criteria": []}), ctx)
    narrow = eligibility_factor(p.with_changes({"exclusion_criteria": ["a", "b", "c", "d", "e", "f"]}), ctx)
    assert 0.3 <= narrow < wide <= 1.2


def test_more_hospitals_shorten_enrolment(base):
    p, ctx = base
    assert projected_enrollment_months(p.with_changes({"number_of_hospitals": 20}), ctx) < projected_enrollment_months(p, ctx)
    assert hospitals_needed(p, ctx) >= 2


def test_max_enrollable_only_for_small_populations(base):
    p, ctx = base
    assert max_enrollable(p, ctx) is None
    rare = load_scenario("rare_disease")
    assert max_enrollable(rare.protocol, rare.context) <= 260


def test_level_index_handles_unknown_values():
    assert level_index(["a", "b"], "b") == 1 and level_index(["a"], "z") == -1


def test_refresh_derived_and_public_report_agree(base):
    p, ctx = base
    q = refresh_derived(p.copy(), ctx)
    report = public_tool_report(q, ctx)
    assert q.power == report["power"] and q.estimated_cost == report["estimated_cost_usd"]
