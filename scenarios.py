"""Scenario definitions: the baseline plus the seven test scenarios of the case study.

Each scenario starts from the baseline and modifies the shared protocol, the public
context and/or the agents' PRIVATE constraints. All values are synthetic.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable

from models import BIOSTATISTICIAN, ETHICS, PATIENT_ADVOCATE, SPONSOR, PrivateState, Protocol, TrialContext
from real_data import validation


@dataclass
class Scenario:
    key: str
    title: str
    description: str
    research_question: str
    protocol: Protocol
    context: TrialContext
    private_states: dict[str, PrivateState]
    regulatory_references: list[str] = field(default_factory=list)
    clinical_guidelines: dict[str, Any] = field(default_factory=dict)
    study_timeline: dict[str, Any] = field(default_factory=dict)


def _baseline_protocol() -> Protocol:
    return Protocol(
        sample_size=320,
        number_of_hospitals=10,
        dosage=100.0,
        dosage_arms=2,
        trial_duration_months=18,
        budget=15_000_000.0,
        alpha=0.05,
        randomization_scheme="block",
        primary_endpoint="binary_response",
        hospital_visits=12,
        remote_monitoring=False,
        invasive_procedures=3,
        inclusion_criteria=["confirmed_diagnosis", "age_18_to_55", "no_prior_therapy"],
        exclusion_criteria=["pregnancy", "severe_renal_impairment", "prior_cancer", "bmi_over_35",
                            "concomitant_medication"],
        safety_monitoring_frequency="monthly",
        adverse_event_reporting="standard_15_day",
    )


def _baseline_context() -> TrialContext:
    return TrialContext(
        drug_profile={
            "name": "SYN-101 (synthetic compound)",
            "reference_dose_mg": 100.0,
            "base_effect_size": 0.42,
            "dose_response_exponent": 0.3,
            "known_risks": ["mild nausea", "transient liver enzyme elevation"],
        },
        cost_model={
            "per_patient_base": 12_000.0,
            "per_visit": 3_000.0,
            "per_invasive_procedure": 5_000.0,
            "remote_monitoring_per_patient": 1_500.0,
            "site_setup": 150_000.0,
            "site_monthly": 10_000.0,
            "per_dose_arm": 1_000_000.0,
            "monitoring_monthly_by_level": [10_000.0, 30_000.0, 50_000.0, 80_000.0],
            "fixed_overhead": 0.0,
        },
        recruitment={
            "base_rate_per_hospital_per_month": 3.0,
            "follow_up_months": 6,
            "eligible_population": None,
            "restrictive_inclusions": ["age_18_to_55", "no_prior_therapy", "treatment_naive_only"],
        },
    )


def _baseline_private_states() -> dict[str, PrivateState]:
    return {
        SPONSOR: PrivateState(
            agent_id=SPONSOR,
            objective="Complete the trial at minimum cost and on schedule.",
            private_constraints={"max_budget_usd": 15_000_000.0, "max_sample_size": 220, "max_duration_months": 18},
            preferences={"target_sample_size": 180, "budget_contingency": 0.05, "power_learning_margin": 0.05},
        ),
        BIOSTATISTICIAN: PrivateState(
            agent_id=BIOSTATISTICIAN,
            objective="Ensure the trial is statistically valid and not underpowered.",
            private_constraints={"min_power": 0.80, "required_alpha": 0.05, "min_invasive_for_biomarker": 1,
                                 "locked_fields": {}},
            preferences={"sample_margin": 0.02},
        ),
        ETHICS: PrivateState(
            agent_id=ETHICS,
            objective="Protect participant safety and welfare.",
            private_constraints={
                "max_dosage_mg": 75.0,
                "min_monitoring_frequency": "monthly",
                "min_ae_reporting": "expedited_7_day",
                "required_exclusions": ["pregnancy", "severe_renal_impairment", "severe_hepatic_impairment"],
                "required_inclusions": [],
                "min_visits_without_remote": 8,
                "min_visits_absolute": 4,
            },
        ),
        PATIENT_ADVOCATE: PrivateState(
            agent_id=PATIENT_ADVOCATE,
            objective="Reduce participant burden and widen access to the trial.",
            private_constraints={
                "max_hospital_visits": 8,
                "max_invasive_procedures": 2,
                "max_exclusion_criteria": 4,
                "restrictive_inclusions": ["age_18_to_55", "no_prior_therapy"],
                "require_remote_monitoring": False,
            },
            preferences={
                "ideal_visits": 6,
                "ideal_invasive": 1,
                "visit_floor": 4,
                "broadening": {"age_18_to_55": "age_18_to_75", "no_prior_therapy": None},
            },
        ),
    }


def baseline() -> Scenario:
    return Scenario(
        key="baseline",
        title="Baseline Phase II Protocol",
        description="Standard Phase II trial; the sponsor's draft is expensive and burdensome.",
        research_question="Can four stakeholders with hidden constraints agree on one protocol?",
        protocol=_baseline_protocol(),
        context=_baseline_context(),
        private_states=_baseline_private_states(),
        regulatory_references=["ICH E6(R2) Good Clinical Practice", "ICH E9 Statistical Principles",
                               "21 CFR 312 (IND regulations)"],
        clinical_guidelines={"phase": "II", "follow_up_months": 6,
                             "real_data_validation": validation(),  # where the starting values sit in real Phase II data
                             "note": "Synthetic guidance for simulation only; not medical advice."},
        study_timeline={"planned_start": "Month 0", "planned_duration_months": 18},
    )


def _derive(key: str, title: str, description: str, question: str,
            modify: Callable[[Scenario], None]) -> Scenario:
    scenario = copy.deepcopy(baseline())
    scenario.key, scenario.title, scenario.description, scenario.research_question = key, title, description, question
    modify(scenario)
    return scenario


def budget_reduction() -> Scenario:
    def modify(s: Scenario) -> None:
        s.protocol.budget = 9_000_000.0
        s.private_states[SPONSOR].private_constraints["max_budget_usd"] = 9_000_000.0
        s.study_timeline["note"] = "Program budget cut by 40%."
    return _derive("budget_reduction", "Budget Reduction", "Trial budget reduced by 40% (15M -> 9M).",
                   "Can the agents still converge on a valid, safe protocol under a tight budget?", modify)


def high_risk_drug() -> Scenario:
    def modify(s: Scenario) -> None:
        s.context.drug_profile["known_risks"] = ["severe hepatotoxicity", "QT prolongation"]
        s.private_states[ETHICS].private_constraints.update({
            "max_dosage_mg": 50.0, "min_monitoring_frequency": "weekly", "min_ae_reporting": "expedited_24h",
            "required_exclusions": ["pregnancy", "severe_renal_impairment", "severe_hepatic_impairment",
                                    "cardiac_arrhythmia"],
            "min_visits_without_remote": 10,
        })
        s.private_states[SPONSOR].private_constraints["max_duration_months"] = 14
        s.protocol.trial_duration_months = 12
        s.study_timeline["note"] = "Sponsor seeks accelerated approval."
    return _derive("high_risk_drug", "High-Risk Drug", "Drug has severe known side effects; sponsor wants speed.",
                   "Does the IRB resist an accelerated, higher-risk design?", modify)


def rare_disease() -> Scenario:
    def modify(s: Scenario) -> None:
        s.context.recruitment.update({"base_rate_per_hospital_per_month": 0.8, "eligible_population": 260})
        s.context.drug_profile["base_effect_size"] = 0.50
        s.protocol.trial_duration_months = 24
        s.private_states[SPONSOR].private_constraints.update({"max_duration_months": 30, "max_budget_usd": 18_000_000.0})
        s.private_states[SPONSOR].preferences["target_sample_size"] = 140
        s.private_states[PATIENT_ADVOCATE].private_constraints["max_exclusion_criteria"] = 3
        s.study_timeline["note"] = "Only ~260 patients are known worldwide."
    return _derive("rare_disease", "Rare Disease", "Very small eligible patient population.",
                   "Can relaxed eligibility be reconciled with the minimum sample size?", modify)


def pediatric() -> Scenario:
    def modify(s: Scenario) -> None:
        s.context.drug_profile.update({"reference_dose_mg": 50.0})
        s.protocol.dosage = 50.0
        s.protocol.inclusion_criteria = ["confirmed_diagnosis", "age_6_to_17", "no_prior_therapy"]
        s.private_states[ETHICS].private_constraints.update({
            "max_dosage_mg": 40.0, "min_monitoring_frequency": "biweekly", "min_ae_reporting": "expedited_24h",
            "required_inclusions": ["parental_consent", "child_assent"], "max_invasive_procedures": 1,
            "min_visits_absolute": 3,
        })
        s.private_states[PATIENT_ADVOCATE].private_constraints.update({
            "max_hospital_visits": 6, "max_invasive_procedures": 1, "require_remote_monitoring": True})
        s.private_states[PATIENT_ADVOCATE].preferences.update({"ideal_visits": 4, "visit_floor": 3})
        s.study_timeline["note"] = "Participants are minors (synthetic scenario)."
    return _derive("pediatric", "Pediatric Trial", "Participants are minors; stricter ethics and advocacy.",
                   "Do added ethical constraints still allow convergence?", modify)


def pandemic() -> Scenario:
    def modify(s: Scenario) -> None:
        s.context.recruitment.update({"follow_up_months": 3, "base_rate_per_hospital_per_month": 5.0})
        s.protocol.trial_duration_months = 9
        s.protocol.budget = 20_000_000.0
        s.private_states[SPONSOR].private_constraints.update({"max_duration_months": 9, "max_budget_usd": 20_000_000.0})
        s.private_states[ETHICS].private_constraints.update({"min_monitoring_frequency": "weekly",
                                                             "min_ae_reporting": "expedited_24h"})
        s.study_timeline["note"] = "Public-health emergency; results needed within 9 months."
    return _derive("pandemic", "Pandemic Trial", "Urgent public-health need for rapid approval.",
                   "Are safety standards preserved under strong time pressure?", modify)


def multi_country() -> Scenario:
    def modify(s: Scenario) -> None:
        s.regulatory_references += ["EU CTR 536/2014", "Japan PMDA GCP Ordinance", "India New Drugs & CT Rules 2019"]
        s.context.cost_model["fixed_overhead"] = 1_500_000.0  # translations, multiple submissions
        s.private_states[SPONSOR].private_constraints["max_budget_usd"] = 16_500_000.0
        # The IRB privately applies the strictest rule from every jurisdiction.
        s.private_states[ETHICS].private_constraints.update({
            "min_monitoring_frequency": "biweekly", "min_ae_reporting": "expedited_7_day",
            "required_exclusions": ["pregnancy", "severe_renal_impairment", "severe_hepatic_impairment",
                                    "participation_in_other_trial"],
        })
        s.study_timeline["note"] = "Sites in US, EU, Japan and India."
    return _derive("multi_country", "Multi-Country Trial", "Different countries impose different requirements.",
                   "Can one protocol satisfy every jurisdiction at once?", modify)


def unexpected_interim() -> Scenario:
    def modify(s: Scenario) -> None:
        s.protocol = Protocol(
            sample_size=200, number_of_hospitals=6, dosage=75.0, dosage_arms=1, trial_duration_months=18,
            budget=11_500_000.0, alpha=0.05, randomization_scheme="stratified_block",
            primary_endpoint="continuous_biomarker", hospital_visits=6, remote_monitoring=True,
            invasive_procedures=1, inclusion_criteria=["confirmed_diagnosis", "age_18_to_75"],
            exclusion_criteria=["pregnancy", "severe_renal_impairment", "severe_hepatic_impairment", "prior_cancer"],
            safety_monitoring_frequency="monthly", adverse_event_reporting="expedited_7_day", status="ACTIVE",
        )
        s.context.drug_profile["known_risks"].append("interim: unexpected grade-3 hepatic events at 75 mg")
        s.private_states[ETHICS].private_constraints.update({
            "max_dosage_mg": 50.0, "min_monitoring_frequency": "weekly", "min_ae_reporting": "expedited_24h"})
        s.private_states[BIOSTATISTICIAN].private_constraints.update({
            "min_sample_size": 120,  # already enrolled
            "locked_fields": {"randomization_scheme": "stratified_block", "primary_endpoint": "continuous_biomarker"},
        })
        s.private_states[SPONSOR].private_constraints.update({"max_sample_size": 260})
        s.private_states[SPONSOR].preferences["target_sample_size"] = 200
        s.study_timeline["note"] = "Interim analysis at month 9 revealed unexpected adverse events."
    return _derive("unexpected_interim", "Unexpected Interim Results",
                   "Interim analysis reveals unexpected adverse events mid-trial.",
                   "Can dosage/monitoring be renegotiated without invalidating the statistics?", modify)


SCENARIOS: dict[str, Callable[[], Scenario]] = {
    "baseline": baseline,
    "budget_reduction": budget_reduction,
    "high_risk_drug": high_risk_drug,
    "rare_disease": rare_disease,
    "pediatric": pediatric,
    "pandemic": pandemic,
    "multi_country": multi_country,
    "unexpected_interim": unexpected_interim,
}


def load_scenario(key: str) -> Scenario:
    """Build a fresh scenario by key (raises KeyError with the valid options)."""
    if key not in SCENARIOS:
        raise KeyError(f"Unknown scenario '{key}'. Choose from: {', '.join(SCENARIOS)}")
    return SCENARIOS[key]()
