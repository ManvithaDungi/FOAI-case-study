"""Hard-constraint checks.

Each `check_<role>` function takes ONE agent's private constraint dict. An agent
calls its own function with its own constraints (self-check). The environment-level
`ConstraintChecker` is the only component that holds every agent's constraints; it
acts as an independent auditor and never shares the details with other agents.
"""

from __future__ import annotations

from typing import Any, Callable

from models import (
    BIOSTATISTICIAN,
    DISPLAY_NAMES,
    ETHICS,
    PATIENT_ADVOCATE,
    SPONSOR,
    Protocol,
    TrialContext,
    Violation,
)
from trial_tools import (
    AE_REPORTING_LEVELS,
    MONITORING_LEVELS,
    calculate_power,
    enrollment_window,
    estimate_cost,
    level_index,
    max_enrollable,
    projected_enrollment_months,
)

Constraints = dict[str, Any]
CheckFunction = Callable[[Protocol, Constraints, TrialContext], list[Violation]]


def _gap(actual: float, limit: float) -> float:
    """Relative size of a violation (used to tell whether a change makes it worse)."""
    return round(abs(actual - limit) / max(abs(limit), 1e-9), 4)


def check_sponsor(protocol: Protocol, c: Constraints, ctx: TrialContext) -> list[Violation]:
    name = DISPLAY_NAMES[SPONSOR]
    out: list[Violation] = []
    cost = estimate_cost(protocol, ctx)
    if cost > c["max_budget_usd"]:
        out.append(Violation(name, f"estimated_cost <= {c['max_budget_usd']:,.0f}", round(cost), "estimated_cost",
                             "decrease", "The projected cost is more than the sponsor can fund.",
                             _gap(cost, c["max_budget_usd"])))
    if protocol.sample_size > c["max_sample_size"]:
        out.append(Violation(name, f"sample_size <= {c['max_sample_size']}", protocol.sample_size, "sample_size",
                             "decrease", "The enrolment target is larger than the sponsor is prepared to run.",
                             _gap(protocol.sample_size, c["max_sample_size"])))
    if protocol.trial_duration_months > c["max_duration_months"]:
        out.append(Violation(name, f"trial_duration_months <= {c['max_duration_months']}",
                             protocol.trial_duration_months, "trial_duration_months", "decrease",
                             "The trial runs longer than the sponsor's development timeline allows.",
                             _gap(protocol.trial_duration_months, c["max_duration_months"])))
    months, window = projected_enrollment_months(protocol, ctx), enrollment_window(protocol, ctx)
    if months > window:
        out.append(Violation(name, f"projected_enrollment_months <= {window}", months, "number_of_hospitals",
                             "increase", "Recruitment cannot finish within the study timeline.", _gap(months, window)))
    pool = max_enrollable(protocol, ctx)
    if pool is not None and protocol.sample_size > pool:
        out.append(Violation(name, f"sample_size <= eligible pool ({pool})", protocol.sample_size,
                             "inclusion_criteria", "broaden",
                             "There are not enough eligible patients to recruit this many participants.",
                             _gap(protocol.sample_size, pool)))
    if protocol.budget + 1 < cost:
        out.append(Violation(name, "allocated budget >= estimated_cost", round(protocol.budget), "budget",
                             "increase", "The allocated budget does not yet cover the projected cost.",
                             _gap(protocol.budget, cost), self_fixable=True))
    return out


def check_biostatistician(protocol: Protocol, c: Constraints, ctx: TrialContext) -> list[Violation]:
    name = DISPLAY_NAMES[BIOSTATISTICIAN]
    out: list[Violation] = []
    power = calculate_power(protocol, ctx)
    if power < c["min_power"]:
        out.append(Violation(name, f"power >= {c['min_power']:.2f}", power, "sample_size", "increase",
                             "Statistical power would be too low; the study would be underpowered.",
                             _gap(power, c["min_power"])))
    if abs(protocol.alpha - c["required_alpha"]) > 1e-9:
        out.append(Violation(name, f"alpha == {c['required_alpha']}", protocol.alpha, "alpha", "set",
                             "The significance level is not acceptable for a confirmatory analysis.",
                             _gap(protocol.alpha, c["required_alpha"])))
    if protocol.sample_size < c.get("min_sample_size", 0):
        out.append(Violation(name, f"sample_size >= {c['min_sample_size']}", protocol.sample_size, "sample_size",
                             "increase", "The sample cannot shrink below participants already committed to the analysis.",
                             _gap(protocol.sample_size, c["min_sample_size"])))
    if protocol.primary_endpoint == "continuous_biomarker" and protocol.invasive_procedures < c.get(
            "min_invasive_for_biomarker", 1):
        out.append(Violation(name, "biomarker endpoint needs >= 1 sampling procedure", protocol.invasive_procedures,
                             "invasive_procedures", "increase",
                             "The primary endpoint cannot be measured without a sampling procedure."))
    for locked_field, locked_value in c.get("locked_fields", {}).items():
        if getattr(protocol, locked_field) != locked_value:
            out.append(Violation(name, f"{locked_field} locked at {locked_value}", getattr(protocol, locked_field),
                                 locked_field, "set",
                                 f"Changing the {locked_field.replace('_', ' ')} mid-study would invalidate the analysis."))
    return out


def check_ethics(protocol: Protocol, c: Constraints, ctx: TrialContext) -> list[Violation]:
    name = DISPLAY_NAMES[ETHICS]
    out: list[Violation] = []
    if protocol.dosage > c["max_dosage_mg"]:
        out.append(Violation(name, f"dosage <= {c['max_dosage_mg']} mg", protocol.dosage, "dosage", "decrease",
                             "The proposed dosage exceeds my safety requirements.",
                             _gap(protocol.dosage, c["max_dosage_mg"])))
    current = level_index(MONITORING_LEVELS, protocol.safety_monitoring_frequency)
    required = level_index(MONITORING_LEVELS, c["min_monitoring_frequency"])
    if current < required:
        out.append(Violation(name, f"monitoring >= {c['min_monitoring_frequency']}",
                             protocol.safety_monitoring_frequency, "safety_monitoring_frequency", "increase",
                             "Safety monitoring is not frequent enough.", float(required - current)))
    current = level_index(AE_REPORTING_LEVELS, protocol.adverse_event_reporting)
    required = level_index(AE_REPORTING_LEVELS, c["min_ae_reporting"])
    if current < required:
        out.append(Violation(name, f"AE reporting >= {c['min_ae_reporting']}", protocol.adverse_event_reporting,
                             "adverse_event_reporting", "increase",
                             "Adverse-event reporting timelines are too slow.", float(required - current)))
    missing = [x for x in c.get("required_exclusions", []) if x not in protocol.exclusion_criteria]
    if missing:
        out.append(Violation(name, f"exclusions include {c['required_exclusions']}", protocol.exclusion_criteria,
                             "exclusion_criteria", "add",
                             "Some high-risk patient groups are not excluded.", float(len(missing))))
    missing = [x for x in c.get("required_inclusions", []) if x not in protocol.inclusion_criteria]
    if missing:
        out.append(Violation(name, f"inclusions include {c['required_inclusions']}", protocol.inclusion_criteria,
                             "inclusion_criteria", "add",
                             "Consent safeguards are missing from the eligibility rules.", float(len(missing))))
    if not protocol.remote_monitoring and protocol.hospital_visits < c["min_visits_without_remote"]:
        out.append(Violation(name, f"visits >= {c['min_visits_without_remote']} unless remote monitoring",
                             protocol.hospital_visits, "remote_monitoring", "enable",
                             "Fewer in-person visits without remote safety monitoring would leave participants under-observed.",
                             _gap(protocol.hospital_visits, c["min_visits_without_remote"])))
    if protocol.hospital_visits < c["min_visits_absolute"]:
        out.append(Violation(name, f"visits >= {c['min_visits_absolute']}", protocol.hospital_visits,
                             "hospital_visits", "increase", "There are too few in-person safety assessments.",
                             _gap(protocol.hospital_visits, c["min_visits_absolute"])))
    if protocol.invasive_procedures > c.get("max_invasive_procedures", 99):
        out.append(Violation(name, f"invasive_procedures <= {c['max_invasive_procedures']}",
                             protocol.invasive_procedures, "invasive_procedures", "decrease",
                             "The number of invasive procedures is not justified for this population.",
                             _gap(protocol.invasive_procedures, c["max_invasive_procedures"])))
    return out


def check_patient_advocate(protocol: Protocol, c: Constraints, ctx: TrialContext) -> list[Violation]:
    name = DISPLAY_NAMES[PATIENT_ADVOCATE]
    out: list[Violation] = []
    if protocol.hospital_visits > c["max_hospital_visits"]:
        out.append(Violation(name, f"hospital_visits <= {c['max_hospital_visits']}", protocol.hospital_visits,
                             "hospital_visits", "decrease", "Too many hospital visits for participants.",
                             _gap(protocol.hospital_visits, c["max_hospital_visits"])))
    if protocol.invasive_procedures > c["max_invasive_procedures"]:
        out.append(Violation(name, f"invasive_procedures <= {c['max_invasive_procedures']}",
                             protocol.invasive_procedures, "invasive_procedures", "decrease",
                             "Participants are asked to undergo too many invasive procedures.",
                             _gap(protocol.invasive_procedures, c["max_invasive_procedures"])))
    if len(protocol.exclusion_criteria) > c["max_exclusion_criteria"]:
        out.append(Violation(name, f"len(exclusion_criteria) <= {c['max_exclusion_criteria']}",
                             len(protocol.exclusion_criteria), "exclusion_criteria", "decrease",
                             "Eligibility is too narrow; too many patients who could benefit are excluded.",
                             _gap(len(protocol.exclusion_criteria), c["max_exclusion_criteria"])))
    blocked = [x for x in protocol.inclusion_criteria if x in c.get("restrictive_inclusions", [])]
    if blocked:
        out.append(Violation(name, f"no restrictive inclusions {c['restrictive_inclusions']}", blocked,
                             "inclusion_criteria", "broaden", "Inclusion criteria are unnecessarily restrictive.",
                             float(len(blocked))))
    if c.get("require_remote_monitoring") and not protocol.remote_monitoring:
        out.append(Violation(name, "remote_monitoring == True", protocol.remote_monitoring, "remote_monitoring",
                             "enable", "Participants need the option of being monitored from home."))
    return out


CHECK_FUNCTIONS: dict[str, CheckFunction] = {
    SPONSOR: check_sponsor,
    BIOSTATISTICIAN: check_biostatistician,
    ETHICS: check_ethics,
    PATIENT_ADVOCATE: check_patient_advocate,
}


class ConstraintChecker:
    """Environment-level auditor that validates the shared protocol against ALL hard constraints.

    It is the only object holding every agent's constraints. Its detailed output goes to
    the audit log / final report, never into another agent's context.
    """

    def __init__(self, constraints_by_agent: dict[str, Constraints], context: TrialContext) -> None:
        self._constraints = {k: dict(v) for k, v in constraints_by_agent.items()}
        self._context = context

    def _check(self, agent_id: str, protocol: Protocol) -> list[Violation]:
        return CHECK_FUNCTIONS[agent_id](protocol, self._constraints[agent_id], self._context)

    def check_sponsor(self, protocol: Protocol) -> list[Violation]:
        return self._check(SPONSOR, protocol)

    def check_biostatistician(self, protocol: Protocol) -> list[Violation]:
        return self._check(BIOSTATISTICIAN, protocol)

    def check_ethics(self, protocol: Protocol) -> list[Violation]:
        return self._check(ETHICS, protocol)

    def check_patient_advocate(self, protocol: Protocol) -> list[Violation]:
        return self._check(PATIENT_ADVOCATE, protocol)

    def check_all(self, protocol: Protocol) -> dict[str, Any]:
        violations = [v for agent_id in CHECK_FUNCTIONS for v in self._check(agent_id, protocol)]
        return {"valid": not violations, "violations": [v.audit_dict() for v in violations]}
