# Demo script and Q&A preparation

## 5-minute demo flow
1. Problem (30 s): four stakeholders, hidden limits, one protocol.
2. `python main.py` - walk through Round 1: Sponsor cuts sample 320->180; Biostatistician fixes power via endpoint; IRB lowers dose to 75 mg; Advocate asks for fewer visits.
3. Show a blocked proposal (sample 180 blocked, power too low) and the IRB "objection overridden" lines.
4. `python main.py --scenario high_risk_drug --summary` - IRB resists acceleration (50 mg, 12 months).
5. `python main.py --mode compare --scenario all` - MAS 0 violations vs single agent 4-10.
6. `pytest -q` - 96 passed.

## Likely questions
- **Why multi-agent?** Private constraints, independent objectives, veto, per-stakeholder audit trail; a single agent needs every secret in one place.
- **How is information hidden?** Private state guarded in the environment (`PrivateStateAccessError`), each agent only gets its own, public messages are qualitative, `sanitize()` redacts numbers.
- **Agent type?** Goal-based/utility-oriented deliberative agents; the Sponsor learns the hidden power threshold.
- **Environment type?** Partially observable, multi-agent, sequential, deterministic (mock), discrete time.
- **What if agents never agree?** Deadlock after 2 unchanged rounds or max 10 rounds -> NO_CONSENSUS with an unresolved-conflicts report.
- **Is it real LLM negotiation?** Default is deterministic mock for reproducibility; `--llm` uses an LLM with JSON validation, fallback and constraint guard.
- **Is the baseline fair?** It is intentionally naive; it shows silent trade-offs, not that no optimiser could succeed.
- **Limitations?** Synthetic models, hand-written strategies, fixed order, deterministic evaluation.
