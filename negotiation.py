"""NegotiationEngine: runs review -> propose -> cross-evaluate -> apply -> check rounds.

Per round:
  1. Every agent independently reviews the SAME public snapshot (no agent sees another's
     decision for this round, and none sees another's private state).
  2. If all four APPROVE -> CONSENSUS.
  3. Otherwise proposals are processed in authority order (IRB first, then Sponsor,
     Biostatistician, Patient Advocate). For each proposal:
       a. drop fields the proposer does not control,
       b. apply to a copy of the protocol,
       c. every OTHER agent evaluates it against its own private constraints,
       d. blocking objections reject it; if a multi-field proposal is blocked, each field
          is retried on its own (compatible parts are kept, conflicting parts dropped).
  4. Accepted changes form a new protocol version; the ConstraintChecker audits it.
  5. Stop on consensus, deadlock (identical blocked proposals repeated) or max_rounds.
"""

from __future__ import annotations

import json
import time
from typing import Any

from agents import Agent
from environment import ClinicalTrialEnvironment
from logger import EventLogger, format_changes
from models import (
    AGENT_IDS,
    BIOSTATISTICIAN,
    DERIVED_FIELDS,
    DISPLAY_NAMES,
    ETHICS,
    PATIENT_ADVOCATE,
    SPONSOR,
    AgentDecision,
    Decision,
    NegotiationMessage,
    NegotiationRound,
    NegotiationStatus,
    Proposal,
    ProposalReview,
    ProposalStatus,
    Protocol,
    ScenarioResult,
)
from scenarios import Scenario
from trial_tools import public_tool_report

PROCESSING_ORDER: tuple[str, ...] = (ETHICS, SPONSOR, BIOSTATISTICIAN, PATIENT_ADVOCATE)


class NegotiationEngine:
    def __init__(self, environment: ClinicalTrialEnvironment, agents: dict[str, Agent],
                 event_logger: EventLogger | None = None, max_rounds: int = 10, mode_label: str = "mock") -> None:
        if max_rounds < 1:
            raise ValueError("max_rounds must be >= 1")
        self.env = environment
        self.agents = agents
        self.events = event_logger or EventLogger()
        self.max_rounds = max_rounds
        self.mode_label = mode_label

    # ----- public API ---------------------------------------------------
    def run(self, scenario: Scenario) -> ScenarioResult:
        started = time.perf_counter()
        self._post(0, SPONSOR, "INITIAL_PROPOSAL", "Sponsor submits the initial protocol draft for review.",
                   result=f"v{self.env.current_protocol.version}")
        rounds: list[NegotiationRound] = []
        status = NegotiationStatus.NO_CONSENSUS
        previous_signature: tuple[Any, ...] | None = None

        for number in range(1, self.max_rounds + 1):
            self.env.start_round(number)
            rnd = self._run_round(number)
            rounds.append(rnd)
            if all(d.decision == Decision.APPROVE for d in rnd.decisions):
                status = NegotiationStatus.CONSENSUS
                break
            signature = self._signature(rnd)
            nothing_accepted = not any(p.accepted_changes for p in rnd.proposals)
            if nothing_accepted and signature == previous_signature:
                status = NegotiationStatus.DEADLOCK
                break
            previous_signature = signature if nothing_accepted else None

        return self._build_result(scenario, rounds, status, time.perf_counter() - started)

    # ----- one round ---------------------------------------------------
    def _run_round(self, number: int) -> NegotiationRound:
        shared = self.env.get_shared_state()
        protocol = shared.protocol
        rnd = NegotiationRound(number, protocol.version)

        for agent_id in AGENT_IDS:  # independent reviews of the same snapshot
            decision = self.agents[agent_id].review_protocol(protocol.copy(), shared)
            rnd.decisions.append(decision)
            self._post(number, agent_id, "REVIEW", decision.reason, decision.proposed_changes,
                       decision.requests, decision.decision.value)
        if all(d.decision == Decision.APPROVE for d in rnd.decisions):
            return rnd

        decisions = {d.agent: d for d in rnd.decisions}
        candidate = protocol.copy()
        for agent_id in PROCESSING_ORDER:
            decision = decisions[agent_id]
            if decision.proposed_changes:
                proposal = Proposal(agent_id, dict(decision.proposed_changes), decision.reason, number,
                                    proposal_id=f"R{number}-{agent_id}")
                candidate = self.process_proposal(proposal, candidate)
                rnd.proposals.append(proposal)

        changes = {k: v for k, v in candidate.to_dict().items()
                   if k not in DERIVED_FIELDS | {"version", "status"} and getattr(protocol, k) != v}
        updated = self.env.apply_proposal(changes)
        audit = self.env.constraint_checker.check_all(updated)
        rnd.protocol_after = updated.to_dict()
        rnd.open_violations = len(audit["violations"])
        # Audit details stay in the private log; the public board only sees a count.
        self.events.log_event(number, "ConstraintChecker", "AUDIT", "", {}, audit)
        self._post(number, "environment", "PROTOCOL_UPDATE",
                   f"Protocol v{updated.version}; {rnd.open_violations} open issue(s) remain.")
        return rnd

    def process_proposal(self, proposal: Proposal, candidate: Protocol) -> Protocol:
        """Validate, cross-evaluate and (partially) apply one proposal. Returns the new candidate."""
        proposer = self.agents[proposal.agent]
        authorized: dict[str, Any] = {}
        for name, value in proposal.changes.items():
            if name in proposer.controlled_decisions and name not in DERIVED_FIELDS:
                authorized[name] = value
            else:
                proposal.rejected_changes[name] = value
                proposal.objections.append(f"Environment: {proposer.name} is not authorised to modify '{name}'.")
                self.events.log_event(proposal.round_number, proposer.name, "UNAUTHORIZED_CHANGE",
                                      f"Attempted to modify {name}", {name: value}, "REJECTED")

        feedback: dict[str, Any] = {"round": proposal.round_number, "fields": {}}
        if authorized:
            trial = self.env.preview(candidate, authorized)
            reviews = self._collect_reviews(proposer, candidate, trial, proposal)
            if not self._is_blocked(proposer, reviews):
                candidate = self._accept(proposal, authorized, trial, reviews, feedback)
            elif len(authorized) > 1:
                for name, value in authorized.items():
                    trial = self.env.preview(candidate, {name: value})
                    reviews = self._collect_reviews(proposer, candidate, trial, proposal)
                    if self._is_blocked(proposer, reviews):
                        self._block(proposal, {name: value}, trial, reviews, feedback)
                    else:
                        candidate = self._accept(proposal, {name: value}, trial, reviews, feedback)
            else:
                self._block(proposal, authorized, trial, reviews, feedback)

        proposal.status = self._status(proposal)
        proposer.receive_feedback(feedback)
        self._post(proposal.round_number, proposal.agent, "PROPOSAL_RESULT",
                   self._summary(proposal), proposal.accepted_changes, result=proposal.status.value)
        return candidate

    # ----- helpers -------------------------------------------------------
    def _collect_reviews(self, proposer: Agent, before: Protocol, after: Protocol,
                         proposal: Proposal) -> list[ProposalReview]:
        return [agent.evaluate_proposal(before, after, proposal, self.env.context)
                for agent_id, agent in self.agents.items() if agent_id != proposer.agent_id]

    @staticmethod
    def _is_blocked(proposer: Agent, reviews: list[ProposalReview]) -> bool:
        if proposer.overrides_objections:
            return False
        return any(not r.accept and r.can_block for r in reviews)

    def _accept(self, proposal: Proposal, changes: dict[str, Any], trial: Protocol,
                reviews: list[ProposalReview], feedback: dict[str, Any]) -> Protocol:
        proposal.accepted_changes.update(changes)
        report = public_tool_report(trial, self.env.context)
        for name, value in changes.items():
            feedback["fields"][name] = {"value": value, "accepted": True, "objections": [],
                                        "evaluated_tool_report": report}
        for r in reviews:
            if not r.accept:
                label = "OBJECTION_OVERRIDDEN" if r.can_block else "ADVISORY_OBJECTION"
                proposal.objections.append(f"{DISPLAY_NAMES[r.reviewer]} ({label.lower()}): {r.reason}")
                self._post(proposal.round_number, r.reviewer, label, r.reason, changes)
        return trial

    def _block(self, proposal: Proposal, changes: dict[str, Any], trial: Protocol,
               reviews: list[ProposalReview], feedback: dict[str, Any]) -> None:
        proposal.rejected_changes.update(changes)
        objections = [r for r in reviews if not r.accept]
        report = public_tool_report(trial, self.env.context)
        for name, value in changes.items():
            feedback["fields"][name] = {"value": value, "accepted": False,
                                        "objections": [r.reason for r in objections],
                                        "evaluated_tool_report": report}
        for r in objections:
            label = "OBJECTION" if r.can_block else "ADVISORY_OBJECTION"
            proposal.objections.append(f"{DISPLAY_NAMES[r.reviewer]}: {r.reason}")
            self._post(proposal.round_number, r.reviewer, label, r.reason, changes, result="BLOCKS")

    @staticmethod
    def _status(proposal: Proposal) -> ProposalStatus:
        if proposal.accepted_changes and not proposal.rejected_changes:
            return ProposalStatus.ACCEPTED
        if proposal.accepted_changes:
            return ProposalStatus.PARTIALLY_ACCEPTED
        return ProposalStatus.REJECTED

    @staticmethod
    def _summary(proposal: Proposal) -> str:
        parts = []
        if proposal.accepted_changes:
            parts.append(f"accepted {format_changes(proposal.accepted_changes)}")
        if proposal.rejected_changes:
            parts.append(f"blocked {format_changes(proposal.rejected_changes)}")
        return "; ".join(parts) or "no changes"

    @staticmethod
    def _signature(rnd: NegotiationRound) -> tuple[Any, ...]:
        return tuple(sorted((p.agent, json.dumps(p.changes, sort_keys=True, default=str)) for p in rnd.proposals)) + \
            tuple(sorted((d.agent, d.decision.value, json.dumps(d.requests, sort_keys=True)) for d in rnd.decisions))

    def _post(self, round_number: int, agent_id: str, action: str, content: str,
              proposal: dict[str, Any] | None = None, requests: dict[str, str] | None = None,
              result: str = "") -> None:
        sender = DISPLAY_NAMES.get(agent_id, agent_id)
        self.env.add_message(NegotiationMessage(round_number, sender, action, content, dict(proposal or {}),
                                                dict(requests or {}), result))
        self.events.log_event(round_number, sender, action, content,
                              {**(proposal or {}), **({"requests": requests} if requests else {})}, result)

    def _build_result(self, scenario: Scenario, rounds: list[NegotiationRound], status: NegotiationStatus,
                      elapsed: float) -> ScenarioResult:
        self.env.set_status("APPROVED" if status == NegotiationStatus.CONSENSUS else "UNRESOLVED")
        final = self.env.current_protocol.copy()
        check = self.env.constraint_checker.check_all(final)
        proposals = [p for r in rounds for p in r.proposals]
        last: dict[str, AgentDecision] = {d.agent: d for d in rounds[-1].decisions} if rounds else {}
        unresolved = [{"agent": DISPLAY_NAMES[a], "position": d.reason}
                      for a, d in last.items() if d.decision != Decision.APPROVE]
        metrics = {
            "consensus_achieved": status == NegotiationStatus.CONSENSUS,
            "rounds": len(rounds),
            "proposals_total": len(proposals),
            "proposals_accepted": sum(p.status == ProposalStatus.ACCEPTED for p in proposals),
            "proposals_partially_accepted": sum(p.status == ProposalStatus.PARTIALLY_ACCEPTED for p in proposals),
            "proposals_rejected": sum(p.status == ProposalStatus.REJECTED for p in proposals),
            "field_changes_accepted": sum(len(p.accepted_changes) for p in proposals),
            "field_changes_blocked": sum(len(p.rejected_changes) for p in proposals),
            "objections_total": sum(len(p.objections) for p in proposals),
            "constraint_violations": len(check["violations"]),
            "protocol_versions": final.version,
            "negotiation_duration_seconds": round(elapsed, 3),
            "mode": self.mode_label,
        }
        self.events.log_event(len(rounds), "environment", "FINAL", status.value, {}, metrics)
        return ScenarioResult(scenario.key, scenario.title, self.mode_label, status, rounds, final, check,
                              metrics, unresolved, self.env.get_negotiation_history())
