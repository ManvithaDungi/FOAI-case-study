"""Event logging (JSON lines audit trail) and human-readable report formatting."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from models import DISPLAY_NAMES, NegotiationStatus, Protocol, ScenarioResult, utc_now

LINE = "=" * 60
THIN = "-" * 60


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class EventLogger:
    """Collects every negotiation event with timestamp/round/agent/action/reason/proposal/result."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._log = logging.getLogger("negotiation")

    def log_event(self, round_number: int, agent: str, action: str, reason: str = "",
                  proposal: dict[str, Any] | None = None, result: Any = "") -> None:
        event = {"timestamp": utc_now(), "round": round_number, "agent": agent, "action": action,
                 "reason": reason, "proposal": proposal or {}, "result": result}
        self.events.append(event)
        self._log.debug(json.dumps(event, default=str))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for event in self.events:
                handle.write(json.dumps(event, default=str) + "\n")


# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------

def _fmt_value(name: str, value: Any) -> str:
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if name in {"budget", "estimated_cost"} and is_number:  # requests carry text like "decrease"
        return f"${value / 1e6:.2f}M"
    if name == "power" and is_number:
        return f"{value:.3f}"
    if isinstance(value, list):
        return ", ".join(value) if value else "(none)"
    return str(value)


def format_changes(changes: dict[str, Any]) -> str:
    return "; ".join(f"{k}={_fmt_value(k, v)}" for k, v in changes.items())


def format_protocol(protocol: Protocol) -> str:
    rows = [
        ("Sample size", protocol.sample_size), ("Hospitals", protocol.number_of_hospitals),
        ("Dosage", f"{protocol.dosage:g} mg"), ("Dose arms (+placebo)", protocol.dosage_arms),
        ("Trial duration", f"{protocol.trial_duration_months} months"),
        ("Budget allocated", _fmt_value("budget", protocol.budget)),
        ("Estimated cost", _fmt_value("estimated_cost", protocol.estimated_cost)),
        ("Power", _fmt_value("power", protocol.power)), ("Alpha", protocol.alpha),
        ("Randomization", protocol.randomization_scheme), ("Primary endpoint", protocol.primary_endpoint),
        ("Hospital visits", protocol.hospital_visits), ("Remote monitoring", protocol.remote_monitoring),
        ("Invasive procedures", protocol.invasive_procedures),
        ("Inclusion criteria", _fmt_value("x", protocol.inclusion_criteria)),
        ("Exclusion criteria", _fmt_value("x", protocol.exclusion_criteria)),
        ("Safety monitoring", protocol.safety_monitoring_frequency),
        ("AE reporting", protocol.adverse_event_reporting),
        ("Projected enrolment", f"{protocol.projected_enrollment_months} months"),
        ("Version / status", f"v{protocol.version} / {protocol.status}"),
    ]
    return "\n".join(f"  {label:<22} {value}" for label, value in rows)


def format_rounds(result: ScenarioResult) -> str:
    out: list[str] = []
    for rnd in result.rounds:
        out += ["", f"Round {rnd.round_number}  (reviewing protocol v{rnd.protocol_version})", "-" * 40]
        for d in rnd.decisions:
            out.append(f"\n{DISPLAY_NAMES[d.agent]}: {d.decision.value}" + (f"  [{d.source}]" if d.source != "mock" else ""))
            out.append(f"  Reason: {d.reason}")
            if d.proposed_changes:
                out.append(f"  Proposes: {format_changes(d.proposed_changes)}")
            if d.requests:
                out.append(f"  Requests: {format_changes(d.requests)}")
        if rnd.proposals:
            out.append("\n  Proposal outcomes:")
            for p in rnd.proposals:
                out.append(f"   - {DISPLAY_NAMES[p.agent]}: {p.status.value}")
                if p.accepted_changes:
                    out.append(f"       accepted: {format_changes(p.accepted_changes)}")
                if p.rejected_changes:
                    out.append(f"       blocked:  {format_changes(p.rejected_changes)}")
                for objection in p.objections:
                    out.append(f"       objection: {objection}")
            out.append(f"  Constraint checker: {rnd.open_violations} open violation(s) after this round")
        out.append(THIN)
    return "\n".join(out)


def format_transcript(result: ScenarioResult) -> str:
    out = [LINE, "NEGOTIATION TRANSCRIPT (public board)", LINE]
    current = -1
    for msg in result.transcript:
        if msg.round_number != current:
            current = msg.round_number
            out.append(f"\n[Round {current}]")
        detail = f" {{{format_changes(msg.proposal)}}}" if msg.proposal else ""
        result_text = f" -> {msg.result}" if msg.result else ""
        out.append(f"{msg.sender} [{msg.action}]{result_text}: {msg.content}{detail}")
    return "\n".join(out)


def format_result(result: ScenarioResult, show_transcript: bool = True) -> str:
    m = result.metrics
    out = [LINE, "MULTI-AGENT CLINICAL TRIAL NEGOTIATION", LINE, f"\nScenario: {result.title}",
           f"Mode: {result.mode}", format_rounds(result), "", LINE, "FINAL RESULT", LINE,
           f"\nStatus: {result.status.value}", f"Negotiation rounds: {m['rounds']}",
           f"Proposals: {m['proposals_total']} (accepted {m['proposals_accepted']}, "
           f"partially {m['proposals_partially_accepted']}, rejected {m['proposals_rejected']})",
           f"Objections raised: {m['objections_total']}", f"Duration: {m['negotiation_duration_seconds']}s",
           "\nFinal Protocol:", format_protocol(result.final_protocol),
           f"\nConstraint violations (independent checker): {m['constraint_violations']}"]
    for v in result.constraint_check["violations"]:
        out.append(f"  - {v['agent']}: {v['constraint']} (actual: {v['actual']})")
    if result.status != NegotiationStatus.CONSENSUS:
        out.append("\nUnresolved conflicts:")
        out += [f"  - {c['agent']}: {c['position']}" for c in result.unresolved_conflicts]
    out.append(LINE)
    if show_transcript:
        out += ["", format_transcript(result)]
    return "\n".join(out)
