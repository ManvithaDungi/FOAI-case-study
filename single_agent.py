"""Single-agent baseline: ONE reasoning process with all objectives blended.

Deliberately simple. It exists to show the architectural contrast:
  * it must be given every stakeholder's private constraints (no information asymmetry),
  * it optimises one weighted score (trade-offs are silent, constraints become soft),
  * nobody can veto its output and there is no per-stakeholder audit trail.
The independent ConstraintChecker is run on its output afterwards.
"""

from __future__ import annotations

import itertools
import json
import logging
import time
from typing import Any

from constraints import ConstraintChecker
from llm import ChatClient, LLMError, extract_json
from logger import LINE, format_protocol
from models import BIOSTATISTICIAN, ETHICS, PATIENT_ADVOCATE, SPONSOR, Protocol
from scenarios import Scenario
from trial_tools import STANDARD_DOSES, calculate_power, estimate_cost, hospitals_needed, refresh_derived

log = logging.getLogger(__name__)

WEIGHTS = {"cost": 0.35, "power": 0.25, "safety": 0.20, "burden": 0.20}


class SingleAgentPlanner:
    """Produces a protocol in one pass from a blended objective."""

    def __init__(self, scenario: Scenario, llm_client: ChatClient | None = None) -> None:
        self.scenario = scenario
        self.context = scenario.context
        # The single agent needs EVERY private constraint - the very thing a MAS keeps private.
        self.all_constraints = {k: v.private_constraints for k, v in scenario.private_states.items()}
        self._llm = llm_client

    def _score(self, p: Protocol) -> float:
        s, b, e, a = (self.all_constraints[k] for k in (SPONSOR, BIOSTATISTICIAN, ETHICS, PATIENT_ADVOCATE))
        cost = estimate_cost(p, self.context) / s["max_budget_usd"]
        power_gap = max(0.0, b["min_power"] - calculate_power(p, self.context)) * 5
        safety_gap = max(0.0, p.dosage - e["max_dosage_mg"]) / e["max_dosage_mg"]
        burden = p.hospital_visits / a["max_hospital_visits"] + p.invasive_procedures / a["max_invasive_procedures"]
        return (WEIGHTS["cost"] * cost + WEIGHTS["power"] * power_gap
                + WEIGHTS["safety"] * safety_gap + WEIGHTS["burden"] * burden / 2)

    def _grid_search(self) -> Protocol:
        base = self.scenario.protocol
        doses = [d for d in STANDARD_DOSES if d <= base.dosage] or [base.dosage]
        best, best_score = base, float("inf")
        for n, arms, dose, visits, remote, invasive in itertools.product(
                range(100, 401, 10), (1, 2), doses, (4, 6, 8, 10, 12), (True, False), (1, 2, 3)):
            p = base.with_changes({"sample_size": n, "dosage_arms": arms, "dosage": float(dose),
                                   "hospital_visits": visits, "remote_monitoring": remote,
                                   "invasive_procedures": invasive})
            p.number_of_hospitals = hospitals_needed(p, self.context)
            score = self._score(p)
            if score < best_score:
                best, best_score = p, score
        return best

    def _llm_plan(self) -> Protocol | None:
        prompt = {
            "task": "Design ONE Phase II protocol balancing all stakeholders. Return JSON with protocol fields.",
            "all_stakeholder_objectives": {k: v.objective for k, v in self.scenario.private_states.items()},
            "all_stakeholder_constraints": self.all_constraints,
            "initial_protocol": self.scenario.protocol.to_dict(),
            "trial_context": self.context.to_dict(),
        }
        messages = [{"role": "system", "content": "You are a single clinical-trial planning assistant. "
                                                  "Respond with a JSON object of protocol fields only."},
                    {"role": "user", "content": json.dumps(prompt, default=str)}]
        try:
            data = extract_json(self._llm.complete(messages))  # type: ignore[union-attr]
        except (LLMError, ValueError) as exc:
            log.warning("Single-agent LLM failed (%s); using grid search.", exc)
            return None
        base = self.scenario.protocol
        allowed = {k: v for k, v in data.items() if hasattr(base, k) and type(getattr(base, k)) is type(v)}
        return base.with_changes(allowed)

    def plan(self) -> dict[str, Any]:
        started = time.perf_counter()
        protocol = (self._llm_plan() if self._llm else None) or self._grid_search()
        protocol = refresh_derived(protocol, self.context)
        protocol.budget = protocol.estimated_cost
        protocol.status = "GENERATED (no stakeholder approval)"
        check = ConstraintChecker(self.all_constraints, self.context).check_all(protocol)
        return {
            "scenario": self.scenario.key,
            "title": self.scenario.title,
            "mode": "single-agent baseline" + (" (llm)" if self._llm else " (mock)"),
            "reasoning_processes": 1,
            "private_information_preserved": False,
            "independent_vetoes": False,
            "negotiation_rounds": 1,
            "blended_weights": WEIGHTS,
            "final_protocol": protocol.to_dict(),
            "constraint_check": check,
            "constraint_violations": len(check["violations"]),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "_protocol": protocol,
        }


def format_single_agent(result: dict[str, Any]) -> str:
    out = [LINE, "SINGLE-AGENT BASELINE", LINE, f"\nScenario: {result['title']}", f"Mode: {result['mode']}",
           "\nArchitecture:", "  - one reasoning process with one blended objective "
           f"(weights {result['blended_weights']})",
           "  - required access to ALL four stakeholders' private constraints",
           "  - no negotiation, no vetoes, no per-stakeholder audit trail",
           "\nGenerated Protocol:", format_protocol(result["_protocol"]),
           f"\nConstraint violations (independent checker): {result['constraint_violations']}"]
    out += [f"  - {v['agent']}: {v['constraint']} (actual: {v['actual']})" for v in result["constraint_check"]["violations"]]
    out.append(LINE)
    return "\n".join(out)
