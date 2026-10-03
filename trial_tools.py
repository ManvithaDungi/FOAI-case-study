"""PUBLIC calculation tools shared by every agent.

These represent the "tool-assisted reasoning" of the case study: any agent may
compute power, cost or recruitment time for a protocol. What an agent does
NOT know is the private threshold another agent applies to these numbers.

The formulas are deliberately simple, synthetic approximations.
"""

from __future__ import annotations

import math

from models import Protocol, TrialContext

MONITORING_LEVELS: list[str] = ["quarterly", "monthly", "biweekly", "weekly"]
AE_REPORTING_LEVELS: list[str] = ["standard_15_day", "expedited_7_day", "expedited_24h"]
ENDPOINT_FACTORS: dict[str, float] = {
    "binary_response": 0.90,
    "change_from_baseline_score": 1.00,
    "continuous_biomarker": 1.10,  # needs at least one sampling procedure
}
RANDOMIZATION_FACTORS: dict[str, float] = {"simple": 0.97, "block": 1.00, "stratified_block": 1.05}
STANDARD_DOSES: list[float] = [10, 20, 25, 30, 40, 50, 60, 75, 100, 125, 150]


def level_index(levels: list[str], value: str) -> int:
    """Position of `value` in an ordered list of levels (-1 if unknown)."""
    return levels.index(value) if value in levels else -1


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def z_quantile(p: float) -> float:
    """Inverse standard-normal CDF via bisection (no SciPy needed)."""
    low, high = -10.0, 10.0
    for _ in range(100):
        mid = (low + high) / 2.0
        if normal_cdf(mid) < p:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def effect_size(protocol: Protocol, context: TrialContext) -> float:
    """Standardised effect size: grows with dose, endpoint sensitivity and design efficiency."""
    drug = context.drug_profile
    dose_ratio = max(protocol.dosage, 0.0) / drug["reference_dose_mg"]
    dose_effect = drug["base_effect_size"] * dose_ratio ** drug["dose_response_exponent"]
    endpoint = ENDPOINT_FACTORS.get(protocol.primary_endpoint, 1.0)
    design = RANDOMIZATION_FACTORS.get(protocol.randomization_scheme, 1.0)
    return dose_effect * endpoint * design


def calculate_power(protocol: Protocol, context: TrialContext) -> float:
    """Two-sided, two-sample power for each dose arm versus placebo."""
    arms = protocol.dosage_arms + 1
    per_arm = protocol.sample_size / arms
    if per_arm <= 1 or protocol.alpha <= 0:
        return 0.0
    z_alpha = z_quantile(1 - protocol.alpha / 2)
    noncentrality = effect_size(protocol, context) * math.sqrt(per_arm / 2)
    return round(normal_cdf(noncentrality - z_alpha), 4)


def required_sample_size(protocol: Protocol, context: TrialContext, target_power: float) -> int:
    """Smallest total sample size reaching `target_power` (rounded up to a multiple of 5)."""
    d = effect_size(protocol, context)
    if d <= 0:
        return 10_000
    z_alpha = z_quantile(1 - protocol.alpha / 2)
    z_beta = z_quantile(target_power)
    per_arm = 2 * ((z_alpha + z_beta) / d) ** 2
    total = math.ceil(per_arm) * (protocol.dosage_arms + 1)
    return int(math.ceil(total / 5) * 5)


def eligibility_factor(protocol: Protocol, context: TrialContext) -> float:
    """How much of the patient pool qualifies; fewer criteria -> wider eligibility."""
    rec = context.recruitment
    restrictive = set(rec.get("restrictive_inclusions", []))
    n_restrictive = sum(1 for c in protocol.inclusion_criteria if c in restrictive)
    factor = 1.2 - 0.05 * len(protocol.exclusion_criteria) - 0.15 * n_restrictive
    return round(min(1.2, max(0.3, factor)), 3)


def monthly_enrollment(protocol: Protocol, context: TrialContext) -> float:
    rate = context.recruitment["base_rate_per_hospital_per_month"]
    return protocol.number_of_hospitals * rate * eligibility_factor(protocol, context)


def projected_enrollment_months(protocol: Protocol, context: TrialContext) -> float:
    capacity = monthly_enrollment(protocol, context)
    return round(protocol.sample_size / capacity, 1) if capacity > 0 else 999.0


def enrollment_window(protocol: Protocol, context: TrialContext) -> float:
    """Months available for enrolment (duration minus follow-up)."""
    return protocol.trial_duration_months - context.recruitment["follow_up_months"]


def hospitals_needed(protocol: Protocol, context: TrialContext) -> int:
    window = enrollment_window(protocol, context)
    per_hospital = context.recruitment["base_rate_per_hospital_per_month"] * eligibility_factor(protocol, context)
    if window <= 0 or per_hospital <= 0:
        return 999
    return max(2, math.ceil(protocol.sample_size / (window * per_hospital)))


def max_enrollable(protocol: Protocol, context: TrialContext) -> int | None:
    """Upper bound on recruitable patients for small populations (None = unlimited)."""
    pool = context.recruitment.get("eligible_population")
    if pool is None:
        return None
    return int(pool * min(1.0, eligibility_factor(protocol, context)))


def estimate_cost(protocol: Protocol, context: TrialContext) -> float:
    """Synthetic trial cost in USD."""
    cm = context.cost_model
    per_patient = (
        cm["per_patient_base"]
        + cm["per_visit"] * protocol.hospital_visits
        + cm["per_invasive_procedure"] * protocol.invasive_procedures
        + (cm["remote_monitoring_per_patient"] if protocol.remote_monitoring else 0.0)
    )
    sites = protocol.number_of_hospitals * (
        cm["site_setup"] + cm["site_monthly"] * protocol.trial_duration_months
    )
    arms = cm["per_dose_arm"] * protocol.dosage_arms
    level = max(level_index(MONITORING_LEVELS, protocol.safety_monitoring_frequency), 0)
    monitoring = cm["monitoring_monthly_by_level"][level] * protocol.trial_duration_months
    return round(per_patient * protocol.sample_size + sites + arms + monitoring + cm.get("fixed_overhead", 0.0), 2)


def refresh_derived(protocol: Protocol, context: TrialContext) -> Protocol:
    """Recompute derived fields in place and return the protocol."""
    protocol.power = calculate_power(protocol, context)
    protocol.estimated_cost = estimate_cost(protocol, context)
    protocol.projected_enrollment_months = projected_enrollment_months(protocol, context)
    return protocol


def public_tool_report(protocol: Protocol, context: TrialContext) -> dict[str, float | int | None]:
    """Summary of public tool outputs, given to every agent (and LLM prompt)."""
    return {
        "power": calculate_power(protocol, context),
        "estimated_cost_usd": estimate_cost(protocol, context),
        "projected_enrollment_months": projected_enrollment_months(protocol, context),
        "enrollment_window_months": enrollment_window(protocol, context),
        "hospitals_needed_for_timeline": hospitals_needed(protocol, context),
        "eligibility_factor": eligibility_factor(protocol, context),
        "max_enrollable_patients": max_enrollable(protocol, context),
    }
