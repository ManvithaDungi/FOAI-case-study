"""Core data models for the clinical trial negotiation simulation.

All values are synthetic. Nothing here is suitable for real trial design.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Decision(str, Enum):
    """Possible outcomes of an agent's review."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    COUNTER_PROPOSE = "COUNTER_PROPOSE"


class ProposalStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    REJECTED = "REJECTED"


class NegotiationStatus(str, Enum):
    CONSENSUS = "CONSENSUS"
    NO_CONSENSUS = "NO_CONSENSUS"  # round limit reached
    DEADLOCK = "DEADLOCK"  # agents keep repeating the same blocked proposals


SPONSOR = "sponsor"
BIOSTATISTICIAN = "biostatistician"
ETHICS = "ethics_committee"
PATIENT_ADVOCATE = "patient_advocate"
AGENT_IDS: tuple[str, ...] = (SPONSOR, BIOSTATISTICIAN, ETHICS, PATIENT_ADVOCATE)
DISPLAY_NAMES: dict[str, str] = {
    SPONSOR: "Sponsor",
    BIOSTATISTICIAN: "Biostatistician",
    ETHICS: "Ethics Committee",
    PATIENT_ADVOCATE: "Patient Advocate",
}

# Fields computed by the environment's public tools; no agent may set them.
DERIVED_FIELDS: frozenset[str] = frozenset({"power", "estimated_cost", "projected_enrollment_months"})


@dataclass
class Protocol:
    """The SHARED clinical trial protocol document every agent can read."""

    sample_size: int = 320
    number_of_hospitals: int = 10
    dosage: float = 100.0  # mg, synthetic
    dosage_arms: int = 2  # active dose arms (a placebo arm is always added)
    trial_duration_months: int = 18
    budget: float = 15_000_000.0  # budget allocated by the sponsor (public)
    power: float = 0.0  # derived
    alpha: float = 0.05
    randomization_scheme: str = "block"
    primary_endpoint: str = "binary_response"
    hospital_visits: int = 12
    remote_monitoring: bool = False
    invasive_procedures: int = 3
    inclusion_criteria: list[str] = field(default_factory=list)
    exclusion_criteria: list[str] = field(default_factory=list)
    safety_monitoring_frequency: str = "monthly"
    adverse_event_reporting: str = "standard_15_day"
    estimated_cost: float = 0.0  # derived
    projected_enrollment_months: float = 0.0  # derived
    version: int = 1
    status: str = "DRAFT"

    def copy(self) -> "Protocol":
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_changes(self, changes: dict[str, Any]) -> "Protocol":
        """Return a copy with `changes` applied (unknown fields are ignored)."""
        updated = self.copy()
        valid = protocol_field_names()
        for name, value in changes.items():
            if name in valid:
                setattr(updated, name, copy.deepcopy(value))
        return updated


def protocol_field_names() -> set[str]:
    return {f.name for f in fields(Protocol)}


@dataclass
class TrialContext:
    """Public scientific/operational context (drug profile, cost model, recruitment).

    Every agent may read this; it feeds the public calculation tools.
    """

    drug_profile: dict[str, Any]
    cost_model: dict[str, float]
    recruitment: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PrivateState:
    """Information that ONLY the owning agent may read."""

    agent_id: str
    objective: str
    private_constraints: dict[str, Any]
    preferences: dict[str, Any] = field(default_factory=dict)
    approval_status: str = "PENDING"


@dataclass
class Violation:
    """A broken hard constraint.

    `constraint`/`actual` are the auditor's view (may contain thresholds).
    `public_message` is the only part an agent may say out loud.
    """

    agent: str
    constraint: str
    actual: Any
    field: str
    direction: str  # what would help: increase / decrease / enable / add / remove / set
    public_message: str
    severity: float = 1.0
    self_fixable: bool = False  # owner can always fix it alone (e.g. budget allocation)

    def audit_dict(self) -> dict[str, Any]:
        return {"agent": self.agent, "constraint": self.constraint, "actual": self.actual}


@dataclass
class AgentDecision:
    agent: str
    decision: Decision
    reason: str
    proposed_changes: dict[str, Any] = field(default_factory=dict)
    requests: dict[str, str] = field(default_factory=dict)  # field -> direction, aimed at others
    source: str = "mock"  # mock | llm | llm-fallback

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        return data


@dataclass
class ProposalReview:
    reviewer: str
    accept: bool
    reason: str
    can_block: bool


@dataclass
class Proposal:
    agent: str
    changes: dict[str, Any]
    reason: str
    round_number: int = 0
    proposal_id: str = ""
    status: ProposalStatus = ProposalStatus.PENDING
    accepted_changes: dict[str, Any] = field(default_factory=dict)
    rejected_changes: dict[str, Any] = field(default_factory=dict)
    objections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass
class NegotiationMessage:
    """A PUBLIC message on the shared negotiation board."""

    round_number: int
    sender: str
    action: str
    content: str
    proposal: dict[str, Any] = field(default_factory=dict)
    requests: dict[str, str] = field(default_factory=dict)
    result: str = ""
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NegotiationRound:
    round_number: int
    protocol_version: int
    decisions: list[AgentDecision] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    protocol_after: dict[str, Any] = field(default_factory=dict)
    open_violations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_number": self.round_number,
            "protocol_version": self.protocol_version,
            "decisions": [d.to_dict() for d in self.decisions],
            "proposals": [p.to_dict() for p in self.proposals],
            "protocol_after": self.protocol_after,
            "open_violations": self.open_violations,
        }


@dataclass
class ScenarioResult:
    scenario: str
    title: str
    mode: str
    status: NegotiationStatus
    rounds: list[NegotiationRound]
    final_protocol: Protocol
    constraint_check: dict[str, Any]
    metrics: dict[str, Any]
    unresolved_conflicts: list[dict[str, str]]
    transcript: list[NegotiationMessage]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "title": self.title,
            "mode": self.mode,
            "status": self.status.value,
            "metrics": self.metrics,
            "final_protocol": self.final_protocol.to_dict(),
            "constraint_check": self.constraint_check,
            "unresolved_conflicts": self.unresolved_conflicts,
            "rounds": [r.to_dict() for r in self.rounds],
            "transcript": [m.to_dict() for m in self.transcript],
        }
