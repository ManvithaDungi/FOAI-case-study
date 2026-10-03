"""The shared negotiation environment.

SHARED state (readable by everyone): current protocol, public negotiation board,
regulatory references, clinical guidelines, trial budget, timeline, round number.

PRIVATE state: one PrivateState per agent, released ONLY to its owner.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from constraints import ConstraintChecker
from models import NegotiationMessage, PrivateState, Protocol, TrialContext
from scenarios import Scenario
from trial_tools import public_tool_report, refresh_derived


class PrivateStateAccessError(PermissionError):
    """Raised when one agent tries to read another agent's private state."""


@dataclass
class SharedState:
    """Snapshot of everything that is public. Handed to every agent each round."""

    protocol: Protocol
    negotiation_history: list[NegotiationMessage]
    regulatory_references: list[str]
    clinical_guidelines: dict[str, Any]
    trial_context: TrialContext
    trial_budget: float
    study_timeline: dict[str, Any]
    current_round: int
    tool_report: dict[str, Any] = field(default_factory=dict)
    previous_protocol: Protocol | None = None  # the version reviewed in the previous round

    def to_public_dict(self, history_limit: int = 30) -> dict[str, Any]:
        return {
            "current_round": self.current_round,
            "current_protocol": self.protocol.to_dict(),
            "public_tool_report": self.tool_report,
            "trial_budget_allocated": self.trial_budget,
            "study_timeline": self.study_timeline,
            "regulatory_references": self.regulatory_references,
            "clinical_guidelines": self.clinical_guidelines,
            "trial_context": self.trial_context.to_dict(),
            "public_negotiation_history": [m.to_dict() for m in self.negotiation_history[-history_limit:]],
        }


class ClinicalTrialEnvironment:
    """Holds the shared protocol and guards each agent's private state."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario_key = scenario.key
        self.context = scenario.context
        self.regulatory_references = list(scenario.regulatory_references)
        self.clinical_guidelines = dict(scenario.clinical_guidelines)
        self.study_timeline = dict(scenario.study_timeline)
        self.current_round = 0
        self.current_protocol = refresh_derived(scenario.protocol.copy(), self.context)
        self.protocol_versions: list[Protocol] = [self.current_protocol.copy()]
        self._history: list[NegotiationMessage] = []
        self._reviewed_last_round: Protocol | None = None
        self._reviewed_this_round: Protocol | None = None
        self._private_states: dict[str, PrivateState] = copy.deepcopy(scenario.private_states)
        self.constraint_checker = ConstraintChecker(
            {k: v.private_constraints for k, v in self._private_states.items()}, self.context)

    # ----- shared state -------------------------------------------------
    @property
    def trial_budget(self) -> float:
        return self.current_protocol.budget

    def get_shared_state(self) -> SharedState:
        """Public snapshot. Contains NO private constraints of any agent."""
        protocol = self.current_protocol.copy()
        return SharedState(
            protocol=protocol,
            negotiation_history=list(self._history),
            regulatory_references=list(self.regulatory_references),
            clinical_guidelines=dict(self.clinical_guidelines),
            trial_context=copy.deepcopy(self.context),
            trial_budget=self.trial_budget,
            study_timeline=dict(self.study_timeline),
            current_round=self.current_round,
            tool_report=public_tool_report(protocol, self.context),
            previous_protocol=self._reviewed_last_round.copy() if self._reviewed_last_round else None,
        )

    def start_round(self, number: int) -> None:
        """Advance the round counter, remembering which version the last round reviewed."""
        if number > 1:
            self._reviewed_last_round = self._reviewed_this_round
        self._reviewed_this_round = self.current_protocol.copy()
        self.current_round = number

    def add_message(self, message: NegotiationMessage) -> None:
        self._history.append(message)

    def get_negotiation_history(self) -> list[NegotiationMessage]:
        return list(self._history)

    # ----- private state ------------------------------------------------
    def get_private_state(self, agent_id: str, requester_id: str) -> PrivateState:
        """Return a copy of an agent's private state - only to that same agent."""
        if agent_id != requester_id:
            raise PrivateStateAccessError(f"'{requester_id}' may not read the private state of '{agent_id}'.")
        return copy.deepcopy(self._private_states[agent_id])

    def agent_ids(self) -> list[str]:
        return list(self._private_states)

    # ----- protocol updates ---------------------------------------------
    def apply_proposal(self, changes: dict[str, Any]) -> Protocol:
        """Apply already-validated changes to the shared protocol as a new version."""
        if not changes:
            return self.current_protocol
        updated = self.current_protocol.with_changes(changes)
        updated.version = self.current_protocol.version + 1
        self.current_protocol = refresh_derived(updated, self.context)
        self.protocol_versions.append(self.current_protocol.copy())
        return self.current_protocol

    def preview(self, protocol: Protocol, changes: dict[str, Any]) -> Protocol:
        """Return a copy of `protocol` with changes applied and derived fields refreshed."""
        return refresh_derived(protocol.with_changes(changes), self.context)

    def set_status(self, status: str) -> None:
        self.current_protocol.status = status
