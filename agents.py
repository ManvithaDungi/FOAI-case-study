"""Stakeholder agents.

Each agent owns a PrivateState (objective + hidden constraints + preferences) that no
other agent can see. Agents only communicate through public decisions, proposals,
objections and qualitative requests ("decrease visits") - never raw thresholds.

Two reasoning modes:
  * MOCK  - deterministic, role-specific Python strategies (no API key needed)
  * LLM   - an OpenAI-compatible model reasons from the role prompt + ONLY this
            agent's private state + the public shared state. Output is validated JSON;
            on failure the agent retries once and then falls back to its mock strategy.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any

from config import PROMPTS_DIR
from constraints import CHECK_FUNCTIONS
from llm import ChatClient, LLMError, extract_json
from models import (
    BIOSTATISTICIAN,
    DERIVED_FIELDS,
    DISPLAY_NAMES,
    ETHICS,
    PATIENT_ADVOCATE,
    SPONSOR,
    AgentDecision,
    Decision,
    PrivateState,
    Proposal,
    ProposalReview,
    Protocol,
    TrialContext,
    Violation,
)
from trial_tools import (
    AE_REPORTING_LEVELS,
    ENDPOINT_FACTORS,
    MONITORING_LEVELS,
    RANDOMIZATION_FACTORS,
    STANDARD_DOSES,
    calculate_power,
    hospitals_needed,
    level_index,
    max_enrollable,
    refresh_derived,
    required_sample_size,
)

log = logging.getLogger(__name__)

CONTROLLED_FIELDS: dict[str, tuple[str, ...]] = {
    SPONSOR: ("sample_size", "number_of_hospitals", "dosage_arms", "budget", "trial_duration_months",
              "remote_monitoring"),
    BIOSTATISTICIAN: ("sample_size", "randomization_scheme", "primary_endpoint", "alpha"),
    ETHICS: ("dosage", "safety_monitoring_frequency", "adverse_event_reporting", "exclusion_criteria",
             "inclusion_criteria"),
    PATIENT_ADVOCATE: ("inclusion_criteria", "hospital_visits", "invasive_procedures"),
}

ENUM_VALUES: dict[str, list[str]] = {
    "randomization_scheme": list(RANDOMIZATION_FACTORS),
    "primary_endpoint": list(ENDPOINT_FACTORS),
    "safety_monitoring_frequency": MONITORING_LEVELS,
    "adverse_event_reporting": AE_REPORTING_LEVELS,
}
NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "sample_size": (10, 5000), "number_of_hospitals": (1, 200), "dosage": (1, 1000), "dosage_arms": (1, 4),
    "trial_duration_months": (1, 120), "budget": (1, 1e10), "alpha": (0.001, 0.2), "hospital_visits": (0, 50),
    "invasive_procedures": (0, 20),
}
REQUEST_DIRECTIONS = {"increase", "decrease", "enable", "disable", "add", "remove", "broaden", "set"}


def _draft(protocol: Protocol, changes: dict[str, Any], ctx: TrialContext) -> Protocol:
    return refresh_derived(protocol.with_changes(changes), ctx)


def _violation_key(v: Violation) -> tuple[str, str]:
    return (v.field, v.public_message)


class Agent:
    """Base stakeholder agent: private state, self-checks, review/evaluate/approve/reject."""

    can_block: bool = True  # may an objection from this agent block another agent's proposal?
    overrides_objections: bool = False  # are this agent's own amendments binding (regulatory authority)?
    prompt_file: str = ""
    approval_message: str = "All of my requirements are satisfied."

    def __init__(self, agent_id: str, role: str, objective: str, private_constraints: dict[str, Any],
                 controlled_decisions: tuple[str, ...] | list[str], preferences: dict[str, Any] | None = None,
                 llm_client: ChatClient | None = None, prompt_dir: Path = PROMPTS_DIR) -> None:
        self.agent_id = agent_id
        self.role = role
        self.name = DISPLAY_NAMES.get(agent_id, role)
        self._private = PrivateState(agent_id, objective, dict(private_constraints), dict(preferences or {}))
        self.controlled_decisions: frozenset[str] = frozenset(controlled_decisions)
        self._llm = llm_client
        self._prompt_dir = prompt_dir
        self._feedback: list[dict[str, Any]] = []
        self._objections_made: list[dict[str, Any]] = []

    # ----- private accessors (only this agent's own code uses these) ------
    @property
    def objective(self) -> str:
        return self._private.objective

    @property
    def _constraints(self) -> dict[str, Any]:
        return self._private.private_constraints

    @property
    def _prefs(self) -> dict[str, Any]:
        return self._private.preferences

    @property
    def approval_status(self) -> str:
        return self._private.approval_status

    def own_violations(self, protocol: Protocol, ctx: TrialContext, include_self_fixable: bool = True) -> list[Violation]:
        """Check the protocol against MY private constraints only."""
        violations = CHECK_FUNCTIONS[self.agent_id](protocol, self._constraints, ctx)
        return [v for v in violations if include_self_fixable or not v.self_fixable]

    # ----- public behaviour ---------------------------------------------
    def review_protocol(self, protocol: Protocol, shared: Any) -> AgentDecision:
        """Independently review the shared protocol and return a decision."""
        if self._llm is not None:
            decision = self._llm_review(protocol, shared)
            if decision is None:
                decision = self._mock_review(protocol, shared)
                decision.source = "llm-fallback"
            elif decision.decision == Decision.APPROVE and self.own_violations(protocol, shared.trial_context):
                log.info("%s: LLM approved despite hard-constraint violations; using guarded logic.", self.name)
                decision = self._mock_review(protocol, shared)
                decision.source = "llm-guard"
        else:
            decision = self._mock_review(protocol, shared)
        decision.reason = self.sanitize(decision.reason)
        self._private.approval_status = decision.decision.value
        return decision

    def propose_changes(self, protocol: Protocol, shared: Any) -> Proposal | None:
        """Return a Proposal with this agent's amendments, or None if it has none."""
        decision = self.review_protocol(protocol, shared)
        if not decision.proposed_changes:
            return None
        return Proposal(agent=self.agent_id, changes=dict(decision.proposed_changes), reason=decision.reason,
                        round_number=shared.current_round)

    def evaluate_proposal(self, before: Protocol, after: Protocol, proposal: Proposal,
                          ctx: TrialContext) -> ProposalReview:
        """Object if the change introduces or worsens a violation of MY hard constraints."""
        old = {_violation_key(v): v for v in self.own_violations(before, ctx, include_self_fixable=False)}
        new = self.own_violations(after, ctx, include_self_fixable=False)
        worse = [v for v in new if _violation_key(v) not in old or v.severity > old[_violation_key(v)].severity + 1e-6]
        if not worse:
            return ProposalReview(self.agent_id, True, "No objection.", self.can_block)
        self._objections_made.append({"round": proposal.round_number, "proposer": proposal.agent,
                                      "changes": dict(proposal.changes)})
        return ProposalReview(self.agent_id, False, worse[0].public_message, self.can_block)

    def approve(self, protocol: Protocol) -> AgentDecision:
        self._private.approval_status = Decision.APPROVE.value
        return AgentDecision(self.agent_id, Decision.APPROVE, self.approval_message)

    def reject(self, reason: str, requests: dict[str, str] | None = None) -> AgentDecision:
        self._private.approval_status = Decision.REJECT.value
        return AgentDecision(self.agent_id, Decision.REJECT, self.sanitize(reason), requests=dict(requests or {}))

    def receive_feedback(self, feedback: dict[str, Any]) -> None:
        """Engine reports what happened to this agent's proposal (accepted/blocked fields)."""
        self._feedback.append(feedback)

    def requests_from_others(self, shared: Any) -> dict[str, str]:
        """Qualitative requests other agents posted publicly in the previous round.

        A request is dropped as already addressed if its field changed since it was made.
        """
        requests: dict[str, str] = {}
        for msg in shared.negotiation_history:
            if msg.round_number == shared.current_round - 1 and msg.sender != self.name and msg.action == "REVIEW":
                requests.update(msg.requests)
        previous = getattr(shared, "previous_protocol", None)
        if previous is not None:
            requests = {f: d for f, d in requests.items()
                        if not hasattr(previous, f) or getattr(previous, f) == getattr(shared.protocol, f)}
        return requests

    def blocked_fields_last_round(self, shared: Any) -> dict[str, dict[str, Any]]:
        if not self._feedback or self._feedback[-1]["round"] != shared.current_round - 1:
            return {}
        return {f: r for f, r in self._feedback[-1]["fields"].items() if not r["accepted"]}

    # ----- information hygiene -------------------------------------------
    def _private_number_tokens(self) -> list[str]:
        tokens: set[str] = set()

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for item in value.values():
                    visit(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    visit(item)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                v = float(value)
                if 0 < v < 1:
                    tokens.update({f"{v:g}", f"{v * 100:g}%", f"{v * 100:g} %"})
                elif v > 3:
                    tokens.update({f"{v:g}", f"{v:,.0f}", f"{v:.1f}"})
                    if v >= 1e6:
                        tokens.update({f"{v / 1e6:g}M", f"{v / 1e6:g} million", f"{v / 1e6:.1f}M"})
        visit(self._constraints)
        return sorted(tokens, key=len, reverse=True)

    def sanitize(self, text: str) -> str:
        """Redact any literal private threshold from a public message."""
        for token in self._private_number_tokens():
            text = re.sub(rf"(?<![\d.]){re.escape(token)}(?![\d])", "[private]", text)
        return text

    # ----- decision assembly ------------------------------------------------
    def _finalize(self, protocol: Protocol, ctx: TrialContext, changes: dict[str, Any],
                  requests: dict[str, str], notes: list[str]) -> AgentDecision:
        changes = {k: v for k, v in changes.items() if getattr(protocol, k) != v}
        violations = self.own_violations(protocol, ctx)
        if changes:
            reason = " ".join(dict.fromkeys(notes)) or "I propose amendments to protect my stakeholder's interests."
            return AgentDecision(self.agent_id, Decision.COUNTER_PROPOSE, reason, changes, requests)
        if violations:
            reason = " ".join(dict.fromkeys(v.public_message for v in violations))
            for v in violations:
                if v.field not in self.controlled_decisions and v.field not in DERIVED_FIELDS:
                    requests.setdefault(v.field, v.direction)
            return AgentDecision(self.agent_id, Decision.REJECT, reason, {}, requests)
        return AgentDecision(self.agent_id, Decision.APPROVE, self.approval_message, {}, {})

    def _mock_review(self, protocol: Protocol, shared: Any) -> AgentDecision:
        """Default strategy: approve if my constraints hold, otherwise reject with requests."""
        return self._finalize(protocol, shared.trial_context, {}, {}, [])

    # ----- LLM reasoning ------------------------------------------------
    def system_prompt(self) -> str:
        path = self._prompt_dir / self.prompt_file
        return path.read_text(encoding="utf-8") if path.exists() else f"You are the {self.role} agent."

    def build_llm_messages(self, protocol: Protocol, shared: Any) -> list[dict[str, str]]:
        """Prompt = role prompt + MY private state + PUBLIC shared state. Nothing else."""
        context = {
            "your_identity": {"agent_id": self.agent_id, "role": self.role, "objective": self.objective},
            "your_private_constraints": self._constraints,
            "your_private_preferences": self._prefs,
            "fields_you_control": sorted(self.controlled_decisions),
            "requests_from_other_agents_last_round": self.requests_from_others(shared),
            "feedback_on_your_recent_proposals": self._feedback[-3:],
            "shared_state": shared.to_public_dict(),
            "response_format": {
                "decision": "APPROVE | REJECT | COUNTER_PROPOSE",
                "reason": "public explanation - qualitative, NEVER state your private thresholds",
                "proposed_changes": {"<field you control>": "<new value>"},
                "requests": {"<field controlled by others>": "increase|decrease|enable|disable|add|remove|broaden"},
            },
        }
        return [{"role": "system", "content": self.system_prompt()},
                {"role": "user", "content": json.dumps(context, default=str)}]

    def _llm_review(self, protocol: Protocol, shared: Any) -> AgentDecision | None:
        messages = self.build_llm_messages(protocol, shared)
        for attempt in range(2):
            try:
                raw = self._llm.complete(messages)  # type: ignore[union-attr]
                return self._validate_llm_output(extract_json(raw), protocol)
            except (LLMError, ValueError, TypeError) as exc:
                log.warning("%s: invalid LLM output (attempt %d): %s", self.name, attempt + 1, exc)
                messages = messages + [{"role": "user", "content": f"Your previous reply was invalid: {exc}. "
                                                                   "Reply with ONLY the JSON object."}]
        return None

    def _validate_llm_output(self, data: dict[str, Any], protocol: Protocol) -> AgentDecision:
        decision_text = str(data.get("decision", "")).upper().strip()
        if decision_text not in Decision.__members__:
            raise ValueError(f"decision must be APPROVE, REJECT or COUNTER_PROPOSE, got {decision_text!r}")
        reason = data.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        raw_changes = data.get("proposed_changes") or {}
        raw_requests = data.get("requests") or {}
        if not isinstance(raw_changes, dict) or not isinstance(raw_requests, dict):
            raise ValueError("proposed_changes and requests must be objects")
        changes = {name: self._coerce_value(name, value, protocol) for name, value in raw_changes.items()}
        requests = {str(k): str(v).lower() for k, v in raw_requests.items() if str(v).lower() in REQUEST_DIRECTIONS}
        decision = Decision[decision_text]
        if decision == Decision.COUNTER_PROPOSE and not changes:
            decision = Decision.REJECT
        if decision == Decision.APPROVE:
            changes, requests = {}, {}
        return AgentDecision(self.agent_id, decision, reason.strip(), changes, requests, source="llm")

    def _coerce_value(self, name: str, value: Any, protocol: Protocol) -> Any:
        if name not in self.controlled_decisions:
            raise ValueError(f"you do not control field '{name}'")
        current = getattr(protocol, name)
        if isinstance(current, bool):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be true/false")
            return value
        if isinstance(current, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a number")
            low, high = NUMERIC_RANGES.get(name, (-math.inf, math.inf))
            if not low <= value <= high:
                raise ValueError(f"{name}={value} outside plausible range")
            return int(value) if isinstance(current, int) else float(value)
        if isinstance(current, list):
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise ValueError(f"{name} must be a list of strings")
            return list(value)
        if name in ENUM_VALUES and value not in ENUM_VALUES[name]:
            raise ValueError(f"{name} must be one of {ENUM_VALUES[name]}")
        return str(value)


# =====================================================================
# Specialised stakeholders
# =====================================================================

class SponsorAgent(Agent):
    """Pharmaceutical sponsor: minimises cost and time. Learns the hidden power bar from objections."""

    prompt_file = "sponsor.txt"
    approval_message = "The protocol is fundable and fits the development timeline. Sponsor approves."

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._learned_min_power = 0.0  # inferred ONLY from public objections

    def receive_feedback(self, feedback: dict[str, Any]) -> None:
        super().receive_feedback(feedback)
        sample = feedback["fields"].get("sample_size")
        if sample and not sample["accepted"]:
            margin = self._prefs.get("power_learning_margin", 0.05)
            self._learned_min_power = max(self._learned_min_power, sample["evaluated_tool_report"]["power"] + margin)

    def _choose_sample_size(self, draft: Protocol, ctx: TrialContext) -> int:
        cap = self._constraints["max_sample_size"]
        target = int(math.ceil(self._prefs.get("target_sample_size", cap) / 5) * 5)
        for n in range(target, cap + 1, 5):
            if calculate_power(draft.with_changes({"sample_size": n}), ctx) >= self._learned_min_power:
                return min(n, draft.sample_size)
        return min(cap, draft.sample_size)

    def _mock_review(self, protocol: Protocol, shared: Any) -> AgentDecision:
        ctx, c = shared.trial_context, self._constraints
        changes: dict[str, Any] = {}
        notes: list[str] = []
        requests: dict[str, str] = {}
        others = self.requests_from_others(shared)

        if protocol.trial_duration_months > c["max_duration_months"]:
            changes["trial_duration_months"] = c["max_duration_months"]
            notes.append("The trial must be shortened to fit the development plan.")
        draft = _draft(protocol, changes, ctx)
        cost_pressure = draft.estimated_cost > c["max_budget_usd"] or draft.sample_size > c["max_sample_size"]

        if cost_pressure and draft.dosage_arms > 1:
            changes["dosage_arms"] = 1
            notes.append("Dropping a dose arm cuts drug-supply and site costs.")
        if cost_pressure:
            n = self._choose_sample_size(_draft(protocol, changes, ctx), ctx)
            if n < protocol.sample_size:
                changes["sample_size"] = n
                notes.append("Reducing the sample size lowers per-patient cost.")
        if not protocol.remote_monitoring and (others.get("remote_monitoring") == "enable"
                                               or others.get("hospital_visits") == "decrease"):
            changes["remote_monitoring"] = True
            notes.append("I will fund remote monitoring so site visits can be reduced without losing oversight.")

        draft = _draft(protocol, changes, ctx)
        needed = min(hospitals_needed(draft, ctx), 60)
        if needed > draft.number_of_hospitals or (needed < draft.number_of_hospitals and cost_pressure):
            changes["number_of_hospitals"] = needed
            notes.append("Resizing the site network to what recruitment actually requires.")

        draft = _draft(protocol, changes, ctx)
        pool = max_enrollable(draft, ctx)
        if pool is not None and draft.sample_size > pool:
            requests.update({"inclusion_criteria": "broaden", "exclusion_criteria": "decrease"})
            notes.append("We cannot find enough eligible patients; eligibility must widen.")
        if draft.estimated_cost > c["max_budget_usd"]:
            requests.update({"hospital_visits": "decrease", "invasive_procedures": "decrease"})
            notes.append("Costs are still too high; fewer visits and procedures would help.")

        contingency = 1 + self._prefs.get("budget_contingency", 0.05)
        allocation = min(c["max_budget_usd"], math.ceil(draft.estimated_cost * contingency / 100_000) * 100_000)
        needs_update = draft.budget < draft.estimated_cost or draft.budget > draft.estimated_cost * 1.25
        if needs_update and allocation != draft.budget:
            changes["budget"] = float(allocation)
            notes.append("Updating the budget allocation to match the projected cost.")

        decision = self._finalize(protocol, ctx, changes, requests, notes)
        if decision.decision == Decision.REJECT:
            decision.requests.update(requests)
        return decision


class BiostatisticianAgent(Agent):
    """Biostatistician: protects power and alpha; prefers design levers before more patients."""

    prompt_file = "biostatistician.txt"
    approval_message = "The design is adequately powered with a valid analysis plan. Biostatistician approves."

    def _mock_review(self, protocol: Protocol, shared: Any) -> AgentDecision:
        ctx, c = shared.trial_context, self._constraints
        locked = c.get("locked_fields", {})
        changes: dict[str, Any] = {}
        notes: list[str] = []
        requests: dict[str, str] = {}

        for name, value in locked.items():
            if getattr(protocol, name) != value:
                changes[name] = value
                notes.append(f"The {name.replace('_', ' ')} must stay as originally specified.")
        if abs(protocol.alpha - c["required_alpha"]) > 1e-9 and "alpha" not in locked:
            changes["alpha"] = c["required_alpha"]
            notes.append("The significance level must remain at the conventional confirmatory level.")

        draft = _draft(protocol, changes, ctx)
        min_inv = c.get("min_invasive_for_biomarker", 1)
        if draft.primary_endpoint == "continuous_biomarker" and draft.invasive_procedures < min_inv:
            if "primary_endpoint" in locked:
                requests["invasive_procedures"] = "increase"
            else:
                changes["primary_endpoint"] = "change_from_baseline_score"
                notes.append("Without a sampling procedure the endpoint must switch to a clinical score.")
            draft = _draft(protocol, changes, ctx)

        if calculate_power(draft, ctx) < c["min_power"]:
            if "primary_endpoint" not in locked:
                best = "continuous_biomarker" if draft.invasive_procedures >= min_inv else "change_from_baseline_score"
                if ENDPOINT_FACTORS[best] > ENDPOINT_FACTORS[draft.primary_endpoint]:
                    changes["primary_endpoint"] = best
                    notes.append("Switching to a more sensitive primary endpoint recovers statistical power.")
            draft = _draft(protocol, changes, ctx)
            if calculate_power(draft, ctx) < c["min_power"]:
                self._add_stratification(draft, locked, changes, notes)
                draft = _draft(protocol, changes, ctx)
            if calculate_power(draft, ctx) < c["min_power"]:
                margin = self._prefs.get("sample_margin", 0.02)
                n = max(required_sample_size(draft, ctx, c["min_power"] + margin), c.get("min_sample_size", 0))
                changes["sample_size"] = n
                notes.append("The sample size must increase; otherwise the study is underpowered.")
                if draft.dosage_arms > 1:
                    requests["dosage_arms"] = "decrease"
        elif self._recently_blocked_sample_cut(shared):
            self._add_stratification(draft, locked, changes, notes, helping=True)

        draft = _draft(protocol, changes, ctx)
        if draft.sample_size < c.get("min_sample_size", 0):
            changes["sample_size"] = c["min_sample_size"]
            notes.append("Participants already enrolled must remain in the analysis population.")
        return self._finalize(protocol, ctx, changes, requests, notes)

    def _add_stratification(self, draft: Protocol, locked: dict[str, Any], changes: dict[str, Any],
                            notes: list[str], helping: bool = False) -> None:
        if "randomization_scheme" in locked or draft.randomization_scheme == "stratified_block":
            return
        changes["randomization_scheme"] = "stratified_block"
        notes.append("Stratified block randomisation reduces variance"
                     + (" so a leaner sample can still be adequately powered." if helping else "."))

    def _recently_blocked_sample_cut(self, shared: Any) -> bool:
        return any(o["round"] == shared.current_round - 1 and "sample_size" in o["changes"]
                   for o in self._objections_made)


class EthicsAgent(Agent):
    """IRB / Ethics Committee: safety veto. Its safety amendments are binding."""

    prompt_file = "ethics_committee.txt"
    overrides_objections = True
    approval_message = "Participant safety safeguards are adequate. Ethics Committee approves."

    def _mock_review(self, protocol: Protocol, shared: Any) -> AgentDecision:
        ctx, c = shared.trial_context, self._constraints
        changes: dict[str, Any] = {}
        notes: list[str] = []
        requests: dict[str, str] = {}

        if protocol.dosage > c["max_dosage_mg"]:
            safe = [d for d in STANDARD_DOSES if d <= c["max_dosage_mg"]]
            changes["dosage"] = float(max(safe) if safe else c["max_dosage_mg"])
            notes.append("The proposed dosage exceeds my safety requirements; I am lowering it to a safer level.")
        for name, levels, key, text in (
            ("safety_monitoring_frequency", MONITORING_LEVELS, "min_monitoring_frequency",
             "Safety monitoring must be more frequent."),
            ("adverse_event_reporting", AE_REPORTING_LEVELS, "min_ae_reporting",
             "Adverse events must be reported on a faster timeline."),
        ):
            if level_index(levels, getattr(protocol, name)) < level_index(levels, c[key]):
                changes[name] = c[key]
                notes.append(text)

        exclusions = list(protocol.exclusion_criteria)
        missing = [x for x in c.get("required_exclusions", []) if x not in exclusions]
        if missing:
            exclusions += missing
            notes.append("High-risk patient groups must be excluded for their own safety.")
        if self.requests_from_others(shared).get("exclusion_criteria") == "decrease":
            removable = [x for x in exclusions if x not in c.get("required_exclusions", [])]
            if removable:
                exclusions = [x for x in exclusions if x not in removable]
                notes.append("I can drop exclusion criteria that are not safety-critical to widen access.")
        if exclusions != protocol.exclusion_criteria:
            changes["exclusion_criteria"] = exclusions

        inclusions = list(protocol.inclusion_criteria)
        missing = [x for x in c.get("required_inclusions", []) if x not in inclusions]
        if missing:
            changes["inclusion_criteria"] = inclusions + missing
            notes.append("Consent safeguards must be part of the eligibility rules.")

        for v in self.own_violations(_draft(protocol, changes, ctx), ctx):
            if v.field not in self.controlled_decisions:
                requests[v.field] = v.direction
                notes.append(v.public_message)
        return self._finalize(protocol, ctx, changes, requests, notes)


class PatientAdvocateAgent(Agent):
    """Patient advocate: lowers burden and widens access. Advisory only - cannot block proposals."""

    prompt_file = "patient_advocate.txt"
    can_block = False
    approval_message = "The participant burden is acceptable and access is fair. Patient Advocate approves."

    def _mock_review(self, protocol: Protocol, shared: Any) -> AgentDecision:
        ctx, c, p = shared.trial_context, self._constraints, self._prefs
        changes: dict[str, Any] = {}
        notes: list[str] = []
        requests: dict[str, str] = {}
        others = self.requests_from_others(shared)

        visits = protocol.hospital_visits
        if visits > c["max_hospital_visits"]:
            visits = p.get("ideal_visits", c["max_hospital_visits"])
            notes.append("The visit schedule is too burdensome; I propose a lighter schedule.")
        if others.get("hospital_visits") == "decrease" and visits > p.get("visit_floor", 4):
            visits = max(p.get("visit_floor", 4), visits - 2)
            notes.append("I support cutting visits further.")
        if others.get("hospital_visits") == "increase":
            visits = min(c["max_hospital_visits"], visits + 1)
            notes.append("I accept one additional safety visit.")
        if visits != protocol.hospital_visits:
            changes["hospital_visits"] = visits
            if not protocol.remote_monitoring:
                requests["remote_monitoring"] = "enable"
                notes.append("Remote monitoring would let participants stay home safely.")

        invasive = protocol.invasive_procedures
        if invasive > c["max_invasive_procedures"]:
            invasive = min(p.get("ideal_invasive", 1), c["max_invasive_procedures"])
            notes.append("Participants are asked to undergo too many invasive procedures.")
        if others.get("invasive_procedures") == "increase" and invasive < c["max_invasive_procedures"]:
            invasive += 1
            notes.append("I accept one sampling procedure so the endpoint can be measured.")
        elif others.get("invasive_procedures") == "decrease" and invasive > p.get("ideal_invasive", 1):
            invasive -= 1
        if invasive != protocol.invasive_procedures:
            changes["invasive_procedures"] = invasive

        mapping = p.get("broadening", {})
        restrictive = c.get("restrictive_inclusions", [])
        if any(x in restrictive for x in protocol.inclusion_criteria):
            broadened = [mapping.get(x) if x in restrictive else x for x in protocol.inclusion_criteria]
            changes["inclusion_criteria"] = [x for x in broadened if x]
            notes.append("Inclusion criteria should be broadened so more patients can take part.")

        if len(protocol.exclusion_criteria) > c["max_exclusion_criteria"]:
            requests["exclusion_criteria"] = "decrease"
            notes.append("Too many patients are excluded; please narrow the exclusion list.")
        if c.get("require_remote_monitoring") and not protocol.remote_monitoring:
            requests["remote_monitoring"] = "enable"
            notes.append("Participants need the option of being monitored from home.")

        decision = self._finalize(protocol, ctx, changes, requests, notes)
        if decision.decision != Decision.APPROVE:
            decision.requests.update(requests)
        return decision


AGENT_CLASSES: dict[str, type[Agent]] = {
    SPONSOR: SponsorAgent,
    BIOSTATISTICIAN: BiostatisticianAgent,
    ETHICS: EthicsAgent,
    PATIENT_ADVOCATE: PatientAdvocateAgent,
}


def create_agents(environment: Any, llm_client: ChatClient | None = None) -> dict[str, Agent]:
    """Instantiate each agent with ONLY its own private state (fetched as itself)."""
    agents: dict[str, Agent] = {}
    for agent_id in environment.agent_ids():
        state = environment.get_private_state(agent_id, requester_id=agent_id)
        agents[agent_id] = AGENT_CLASSES[agent_id](
            agent_id=agent_id,
            role=DISPLAY_NAMES[agent_id],
            objective=state.objective,
            private_constraints=state.private_constraints,
            controlled_decisions=CONTROLLED_FIELDS[agent_id],
            preferences=state.preferences,
            llm_client=llm_client,
        )
    return agents
