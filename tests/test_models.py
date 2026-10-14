"""Data model tests: Protocol, enums, records (models.py)."""

from __future__ import annotations

from models import (AGENT_IDS, DERIVED_FIELDS, DISPLAY_NAMES, AgentDecision, Decision, NegotiationStatus,
                    Proposal, ProposalStatus, Protocol, protocol_field_names)


def test_protocol_defaults_describe_the_sponsor_draft():
    p = Protocol()
    assert (p.sample_size, p.dosage, p.dosage_arms, p.hospital_visits) == (320, 100.0, 2, 12)
    assert p.version == 1 and p.status == "DRAFT"


def test_protocol_copy_is_independent():
    p = Protocol(exclusion_criteria=["pregnancy"])
    q = p.copy()
    q.exclusion_criteria.append("prior_cancer")
    q.sample_size = 100
    assert p.exclusion_criteria == ["pregnancy"] and p.sample_size == 320


def test_with_changes_returns_new_protocol_and_ignores_unknown_fields():
    p = Protocol()
    q = p.with_changes({"sample_size": 180, "not_a_field": 1})
    assert q.sample_size == 180 and p.sample_size == 320
    assert not hasattr(q, "not_a_field")


def test_to_dict_contains_every_field():
    assert set(Protocol().to_dict()) == protocol_field_names()


def test_derived_fields_are_real_protocol_fields():
    assert DERIVED_FIELDS <= protocol_field_names()


def test_four_agents_each_have_a_display_name():
    assert len(AGENT_IDS) == 4 and set(DISPLAY_NAMES) == set(AGENT_IDS)


def test_enums_serialise_to_their_names():
    assert {d.value for d in Decision} == {"APPROVE", "REJECT", "COUNTER_PROPOSE"}
    assert {s.value for s in NegotiationStatus} == {"CONSENSUS", "NO_CONSENSUS", "DEADLOCK"}
    assert AgentDecision("sponsor", Decision.APPROVE, "ok").to_dict()["decision"] == "APPROVE"


def test_new_proposal_starts_pending_and_serialises_status():
    p = Proposal("sponsor", {"sample_size": 200}, "cut cost")
    assert p.status == ProposalStatus.PENDING
    assert p.to_dict()["status"] == "PENDING"
