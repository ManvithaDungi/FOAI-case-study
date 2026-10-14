# Multi-Agent Clinical Trial Protocol Negotiation

A small working proof-of-concept of the case study *"Multi-Agent Clinical Trial Protocol Negotiation Using
Autonomous AI Agents with Hidden Objectives"* (FOAI 23CSE401).

> **Academic simulation only.** All trial parameters, cost figures, dose-response curves and
> constraints are synthetic. Nothing here is fit for real clinical trial design, regulatory
> submission or medical decision-making, and no patient data is used.

---

## 1. Project overview

Four autonomous stakeholder agents negotiate one shared Phase II protocol:

| Agent | Objective | Example *private* constraints | Controls |
|---|---|---|---|
| **Sponsor** | Minimum cost and time | budget ceiling, sample-size cap, max duration | sample size, hospitals, dose arms, budget, duration, remote monitoring |
| **Biostatistician** | Statistical validity | power ≥ 80 %, alpha = 0.05, locked design fields | sample size, randomization, primary endpoint, alpha |
| **Ethics Committee (IRB)** | Participant safety (**veto**) | max dosage, monitoring level, AE reporting, required exclusions | dosage, monitoring, AE reporting, exclusion/consent criteria |
| **Patient Advocate** | Lower burden, wider access (advisory) | max visits, max invasive procedures, max exclusions | inclusion criteria, visit schedule, invasive procedures |

The protocol is finalised only when **all four approve**. An independent **Constraint Checker** audits
every version.

## 2. Problem being solved

Real protocol design is a negotiation between parties with conflicting goals *and* undisclosed limits.
A single prompt to a single model produces one "averaged" answer: trade-offs are hidden, nobody can veto,
and confidential limits must all be handed to one place.

## 3. Why multi-agent

| Single agent (`single_agent.py`) | Multi-agent (this system) |
|---|---|
| One reasoning process | Four independent reasoning processes |
| One blended, weighted objective | Four separate objectives |
| Must be given **every** private constraint | Each agent sees **only its own** constraints |
| No disagreement, no veto | Explicit objections, IRB veto, all must approve |
| No audit trail per stakeholder | Every decision, objection and amendment is logged |

## 4. Architecture

```
                    +------------------+
                    |   Environment    |
                    | Shared Protocol  |   <- public: protocol, history, guidelines,
                    +--------+---------+      budget, timeline, public calculators
                             |
          +------------------+------------------+
          |          |             |            |
          v          v             v            v
      Sponsor   Biostatistician   IRB    Patient Advocate
       Agent        Agent         Agent       Agent
     [private]    [private]    [private]    [private]     <- hidden objectives/constraints
          |          |             |            |
          +----------+-------------+------------+
                             |
                       Negotiation                <- reviews, proposals, objections,
                             |                       qualitative requests (no numbers)
                             v
                    Constraint Checker            <- only component that sees ALL
                             |                       constraints; results go to the audit
                             v                       log, not to the agents
                    Consensus / Failure
```

| File | Purpose |
|---|---|
| `main.py` | CLI |
| `config.py` | settings / `.env` loading |
| `models.py` | dataclasses: `Protocol`, `AgentDecision`, `Proposal`, `NegotiationMessage`, `NegotiationRound`, `ScenarioResult`, ... |
| `environment.py` | `ClinicalTrialEnvironment` – shared state + guarded private state |
| `agents.py` | `Agent` base class + `SponsorAgent`, `BiostatisticianAgent`, `EthicsAgent`, `PatientAdvocateAgent` |
| `negotiation.py` | `NegotiationEngine` – the round loop |
| `constraints.py` | per-role hard-constraint checks + `ConstraintChecker` |
| `trial_tools.py` | public calculators: power, required sample size, cost, recruitment |
| `scenarios.py` | baseline + 7 scenarios |
| `llm.py` | minimal OpenAI-compatible client (stdlib `urllib`) |
| `logger.py` | JSON-lines event log + report formatting |
| `single_agent.py` | single-agent baseline |
| `prompts/*.txt` | four distinct role prompts |
| `tests/` | pytest suite |

### PEAS summary (for the report)

| | |
|---|---|
| **Performance** | consensus reached, constraint violations = 0, rounds, accepted/blocked proposals |
| **Environment** | shared protocol document + public board; partially observable (private constraints), multi-agent, sequential, deterministic in mock mode |
| **Actuators** | APPROVE / REJECT / COUNTER_PROPOSE, amendments to *own* fields, qualitative requests, objections |
| **Sensors** | current protocol, public history, public tool report (power / cost / recruitment), feedback on own proposals, own private state |

## 5. The four agents

* **Sponsor** – cuts first (drops a dose arm, shrinks sample, resizes hospitals). It never sees the power
  threshold; it **learns** it: each time a sample cut is blocked it records the power of the blocked design
  and next time proposes a sample whose (public) power is higher. It funds remote monitoring when others ask
  for fewer visits.
* **Biostatistician** – protects power and alpha. Uses design levers first (more sensitive endpoint,
  stratified randomisation) and asks for more patients only as a last resort. Respects locked fields mid-trial.
* **Ethics Committee** – safety veto. Its safety amendments are binding (others' objections are logged as
  *overridden*). It can drop non-safety exclusion criteria when asked for wider access.
* **Patient Advocate** – fewer visits/procedures, broader inclusion. Its objections are **advisory**
  (cannot block), but nothing is final without its approval.

## 6. Shared vs private state (information asymmetry)

* Private state lives in `ClinicalTrialEnvironment._private_states`. `get_private_state(agent_id,
  requester_id)` raises `PrivateStateAccessError` unless `agent_id == requester_id`.
* Each agent object is constructed with **only** its own `PrivateState`.
* An LLM prompt contains the role prompt + *that agent's* private state + the public shared state — never
  another agent's constraints (tested).
* Public messages are qualitative. The IRB says *"The proposed dosage exceeds my safety requirements"*,
  never *"max 75 mg"*. Requests carry only a direction (`"hospital_visits": "decrease"`).
* `Agent.sanitize()` redacts any literal private threshold from a public reason (protects LLM mode).
* The Constraint Checker's detailed audit is written to the event log; the public board only gets a count.

## 7. Negotiation workflow

1. Load scenario → environment → four agents (each fetches only its own private state).
2. Sponsor submits the initial draft (round 0).
3. **Each round:** all agents independently review the same snapshot → `APPROVE | REJECT | COUNTER_PROPOSE`.
4. All approve → **CONSENSUS**.
5. Otherwise proposals are processed in authority order: IRB → Sponsor → Biostatistician → Patient Advocate.
   For each proposal: drop unauthorised fields → apply to a copy → every *other* agent evaluates it against
   its own constraints → a blocking objection rejects it; a blocked multi-field proposal is retried field by
   field so compatible parts survive.
6. Accepted changes → new protocol version → Constraint Checker audit.
7. Stop on consensus, **DEADLOCK** (protocol unchanged for two rounds), or `max_rounds` (default 10, **NO_CONSENSUS**).

## 8. Constraint checker

`ConstraintChecker.check_sponsor/…/check_all(protocol)` returns:

```json
{"valid": false, "violations": [{"agent": "Biostatistician", "constraint": "power >= 0.80", "actual": 0.63}]}
```

It is an environment-level auditor and the only object that holds every agent's constraints.

## 9. Scenarios

| Key | Setup | Research question |
|---|---|---|
| `baseline` | 320 patients (real P92), 10 hospitals, 2 dose arms, 100 mg, 12 visits, 3 invasive procedures, $15M | can hidden-constraint agents agree? |
| `budget_reduction` | budget cut 40 % ($9M) | valid, safe protocol under tight cost? |
| `high_risk_drug` | severe side effects, lower dose limit, weekly monitoring; sponsor wants ≤ 14 months | does the IRB resist acceleration? |
| `rare_disease` | ~260 eligible patients, slow recruitment | relaxed eligibility vs minimum sample? |
| `pediatric` | minors: consent/assent, lower dose, ≤ 1 invasive procedure | stricter constraints still converge? |
| `pandemic` | 9-month deadline, urgent | safety preserved under time pressure? |
| `multi_country` | US/EU/Japan/India: IRB applies the strictest rule of each; extra overhead | one protocol for all jurisdictions? |
| `unexpected_interim` | mid-trial AEs: dose limit drops, endpoint/randomisation locked, 120 already enrolled | renegotiate without invalidating the stats? |

## 10. Mock mode

Default. Deterministic role strategies in `agents.py` (`_mock_review`). No API key or network needed.
Same input → same negotiation.

## 11. LLM mode

`python main.py --llm`. Each agent's review is produced by the model from its own prompt file and its own
private state. The response must be JSON:

```json
{"decision": "COUNTER_PROPOSE", "reason": "...", "proposed_changes": {"dosage": 50}, "requests": {"remote_monitoring": "enable"}}
```

Validation: decision value, field ownership, types, enum values, plausible ranges. Invalid output → one
retry → deterministic fallback (`source = llm-fallback`). An LLM "APPROVE" while the agent's own hard
constraints fail is overridden (`source = llm-guard`). Proposal *evaluation* (objections) uses each agent's
deterministic self-check, so hard limits are enforced identically in both modes.

## 12. Installation

```bash
cd clinical_trial_mas
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                          # only pytest; runtime is stdlib-only
```

## 13. Configuration

```bash
cp .env.example .env     # then set OPENAI_API_KEY (and optionally OPENAI_BASE_URL, MODEL)
```

No key → mock mode automatically. Any OpenAI-compatible endpoint (e.g. a local Ollama/LM Studio server)
works via `OPENAI_BASE_URL`.

## 14. Running

```bash
python main.py                                  # baseline scenario, multi-agent, mock, with transcript
python main.py --scenario budget_reduction      # any of the 8 scenario keys
python main.py --mode baseline                  # single-agent baseline
python main.py --mode compare --scenario all    # MAS vs single agent on every scenario
python main.py --summary                        # final result only
python main.py --llm                            # LLM reasoning (falls back to mock without a key)
python main.py --help
streamlit run app.py                            # web UI (pip install streamlit)
python fetch_real_data.py --pages 5             # refresh real Phase II data (needs internet)
pytest -q                                       # tests
```

Outputs per run: `outputs/<scenario>.json`, `outputs/<scenario>.txt`, `outputs/<scenario>_events.jsonl`
(and `<scenario>_single_agent.json` for the baseline).

## 15. Example output (baseline, mock mode - abridged)

Round 1: the IRB lowers the dose to 75 mg (binding); the Sponsor's cut from 320 to 180 patients is blocked
(power 0.64); the Advocate's visit cut is blocked until the Sponsor funds remote monitoring. Round 2: levers
restore power and 180 patients / 4 visits are accepted; consensus in round 4.

```
Status: CONSENSUS
Negotiation rounds: 4
Proposals: 9 (accepted 7, partially 2, rejected 0)
Objections raised: 5
Duration: 0.064s

Final Protocol:
  Sample size            180
  Hospitals              6
  Dosage                 75 mg
  Dose arms (+placebo)   1
  Trial duration         18 months
  Budget allocated       $9.50M
  Estimated cost         $9.01M
  Power                  0.847
  Alpha                  0.05
  Randomization          stratified_block
  Primary endpoint       continuous_biomarker
  Hospital visits        4
  Remote monitoring      True
  Invasive procedures    1
  Inclusion criteria     confirmed_diagnosis, age_18_to_75
  Exclusion criteria     pregnancy, severe_renal_impairment, severe_hepatic_impairment
  Safety monitoring      monthly
  AE reporting           expedited_7_day
  Projected enrolment    9.5 months
  Version / status       v4 / APPROVED
```

`--mode compare --scenario all` (mock):

```
Scenario              MAS status     Rounds MAS viol.  Single viol.
baseline              CONSENSUS           4         0             7
budget_reduction      CONSENSUS           5         0             8
high_risk_drug        CONSENSUS           5         0             9
rare_disease          CONSENSUS           5         0             7
pediatric             CONSENSUS           4         0            10
pandemic              CONSENSUS           4         0             8
multi_country         CONSENSUS           4         0             8
unexpected_interim    CONSENSUS           3         0             4
```

The single-agent baseline is intentionally naive (weighted sum over a few variables, soft penalties). Its
violation count illustrates *silent trade-offs without vetoes*; it is **not** a claim that a well-engineered
single optimiser could never satisfy the constraints. The architectural point is that such an optimiser would
need every party's confidential limits in one place and gives no stakeholder a voice or veto.

## 16. Limitations

* Synthetic, simplified models of power, cost and recruitment; no real pharmacology.
* Mock strategies are hand-written heuristics, so mock-mode results reflect their design.
* Proposal evaluation is deterministic even in LLM mode (by design, for safety and reproducibility).
* Fixed processing order and a simple authority model (IRB binding, Advocate advisory).
* Redaction of private numbers is best-effort string matching.
* All seven scenarios currently reach consensus in mock mode; a deliberately impossible configuration
  (see `tests/test_mas.py::test_negotiation_stops_after_max_rounds`) shows the failure/unresolved path.

## 17. Future improvements

* LLM-based proposal evaluation and argumentation, with the deterministic check as a guard.
* Utility functions and concession curves per agent; game-theoretic / Pareto analysis.
* More stakeholders (CRO, regulator, investigators) and per-country IRB agents.
* Batch experiments with randomised constraint sets and statistics across runs.
* Richer metrics (fairness across agents, concession size, time to agreement).

## Mapping to the case study report

| Report section | Implementation |
|---|---|
| §3 Why MAS | private `PrivateState`, independent `review_protocol`, IRB veto, audit log; `single_agent.py` contrast |
| §5 Proposed environment | `ClinicalTrialEnvironment`, `SharedState` |
| §6 Agent design | `agents.py`, `CONTROLLED_FIELDS`, `scenarios._baseline_private_states` |
| §7 Shared/private state | `get_shared_state()` vs guarded `get_private_state()` |
| §8 Workflow (10 steps) | `NegotiationEngine.run` / `_run_round` / `process_proposal` |
| §9 Walkthrough | baseline scenario: 320→180 blocked (power ≈ 0.64), dose lowered, visits cut once remote monitoring is funded |
| §10 Scenarios | `scenarios.py` (7 + baseline) |
| §10/§11 Metrics & baseline | `ScenarioResult.metrics`, `--mode compare` |

---

# Rubric Documentation (Review 1)

## A. PEAS (detailed)

| | |
|---|---|
| **Performance** | consensus (all 4 approve); constraint violations = 0; rounds; proposals accepted / partial / rejected; objections; field changes accepted vs blocked; power >= 0.80; cost <= budget |
| **Environment** | shared Phase II protocol, public history, guidelines, budget, timeline, public calculators; per-agent private state |
| **Actuators** | APPROVE / REJECT / COUNTER_PROPOSE; amendments to own fields; qualitative requests; objections |
| **Sensors** | current protocol, public history, public tool report, feedback on own proposals, own private constraints |

### Performance metric definitions

| Metric | Definition | Target |
|---|---|---|
| Consensus | all four agents approve the same protocol version | yes |
| Constraint violations | hard-constraint failures from `ConstraintChecker` on final protocol | 0 |
| Rounds | rounds until consensus (max 10) | low |
| Proposal acceptance | (accepted + partial) / total proposals | high |
| Power / Cost | statistical power; estimated cost vs budget | >= 0.80 / <= budget |

### Input -> sensor and output -> actuator mapping

| Agent | Input (sensor) | Output (actuator) |
|---|---|---|
| Sponsor | protocol, public power/cost/recruitment report, feedback on blocked proposals, own budget/sample/duration limits | sample_size, hospitals, dose arms, budget, duration, remote_monitoring; requests to cut visits/procedures |
| Biostatistician | protocol, public power report, own power/alpha limits, locked fields | sample_size, randomization, primary_endpoint, alpha |
| Ethics Committee | protocol, own max dose, monitoring, AE-reporting rules | dosage, monitoring, AE reporting, exclusion/consent (binding veto) |
| Patient Advocate | protocol, own max visits/procedures/exclusions | inclusion criteria, visits, invasive procedures, remote-monitoring request (advisory) |

## B. Agent and environment analysis

**Agent category:** goal-based, utility-oriented rational agents with a model of the shared protocol. Deliberative (reason over protocol + own constraints). The Sponsor has a simple learning component: it records the power of blocked designs and proposes a higher sample next time. System type: mixed cooperative-competitive MAS with heterogeneous authority (IRB veto, advisory Advocate).

| Property | Classification | Why |
|---|---|---|
| Observability | Partially observable | peers' private constraints hidden |
| Agents | Multi-agent, mixed cooperative/competitive | conflicting goals, joint agreement needed |
| Determinism | Deterministic (mock), stochastic (LLM) | same input -> same negotiation in mock mode |
| Episodic/Sequential | Sequential | each round builds on previous version |
| Static/Dynamic | Static between rounds; changes via amendments (and mid-trial in `unexpected_interim`) | |
| Discrete/Continuous | Discrete time; mixed integer/bounded-numeric variables | |
| Known/Unknown | Known rules, hidden peer constraints | |

## C. Design details

### Algorithms used
1. Round-based iterative negotiation over a shared snapshot (independent reviews).
2. Priority-ordered proposal processing: IRB -> Sponsor -> Biostatistician -> Patient Advocate (IRB binding, Advocate advisory).
3. Proposal evaluation: other agents check the amended copy against their own hard constraints; a blocking objection rejects it.
4. Field-by-field fallback so compatible parts of a blocked proposal survive (partial acceptance).
5. Sponsor concession learning from public power of blocked designs.
6. Termination: consensus, deadlock (unchanged 2 rounds), or max_rounds.
7. Rule-based strategies (mock); JSON-validated LLM reasoning with retry, fallback and constraint guard (LLM mode).

### Hardware and software requirements

| Item | Requirement |
|---|---|
| Hardware | any PC, >= 4 GB RAM, no GPU; network only for optional LLM mode |
| OS | Windows / Linux / macOS |
| Language | Python 3.10+ (tested 3.10.11) |
| Runtime libs | standard library only (urllib, dataclasses, argparse, json) |
| Test lib | pytest |
| Optional | OpenAI-compatible API or local Ollama / LM Studio (`--llm`) |

### Tool / package details
Python stdlib (core), pytest (tests), `config.py` `.env` loader, optional OpenAI-compatible HTTP API with role prompts in `prompts/`.

### Scalability and code structure
One module per concern; adding an agent = subclass `Agent` + a prompt file + a `PrivateState` + a constraint check; adding a scenario = one entry in `scenarios.py`; LLM backend swappable via `OPENAI_BASE_URL`. Public/private state is isolated by `ClinicalTrialEnvironment`, so new stakeholders (CRO, regulator) do not change existing agents.

## D. Implementation details

### Input representation
`Protocol` dataclass (`models.py`): sample_size, number_of_hospitals, dosage, dosage_arms, trial_duration_months, budget, power, alpha, randomization_scheme, primary_endpoint, hospital_visits, remote_monitoring, invasive_procedures, inclusion/exclusion criteria, safety_monitoring, adverse_event_reporting. Each agent holds a `PrivateState`. Decisions are `AgentDecision`, amendments `Proposal`, rounds `NegotiationRound`. A scenario = initial protocol + trial context + private states.

### Dataset
The scenarios are **synthetic**, defined in `scenarios.py` with the starting values of the case-study report (320 patients, Sponsor cap 220 / target 180, 10 hospitals, 2 arms, 18 months). They are **validated against real data**: 5,000 completed Phase II interventional trials fetched from the ClinicalTrials.gov API v2 (`fetch_real_data.py`, accessed 2026-10-14; rows in `data/phase2_trials.csv`, statistics in `data/phase2_summary.json`, helper `real_data.py`). Position of the starting values in the real distribution: 320 patients = 92nd percentile, cap 220 = 88th, target 180 = 83rd, 10 hospitals = 54th percentile of multi-site trials, 18 months = 29th percentile; 2 arms is the real median. Real medians: enrolment 56 (IQR 29-122), duration 32 months (IQR 16-57). So the baseline is a deliberately large, expensive Phase II draft, and its reduced final protocol (180) is still above the real 80th percentile. Cost per patient, dose-response and thresholds are not in the registry (cost model after Sertkaya et al. 2016; thresholds after ICH E9). No patient-level data.

### User interface
Web UI (`streamlit run app.py`): scenario picker, round-by-round negotiation view, protocol evolution charts, single-vs-multi-agent comparison and constraint audit. Command-line (`main.py`): `--mode`, `--scenario`, `--llm`, `--max-rounds`, `--no-transcript`, `--summary`, `--output-dir`, `--verbose`. Output: readable transcript + final result, saved to `outputs/`.

## E. Testing and results

### Levels of testing

| Level | File | Verifies |
|---|---|---|
| Unit - tools | `test_trial_tools.py` | power, sample size, cost, recruitment |
| Unit - constraints | `test_constraints.py` | per-role violations, checker |
| Unit - models/utils | `test_models.py`, `test_utils.py` | dataclasses, helpers |
| Algorithm | `test_negotiation_algorithm.py` | authority order, partial acceptance, deadlock, max rounds |
| Integration | `test_mas.py` | private-state guard, no prompt leakage, LLM validation/fallback, end-to-end |
| Scenario | `test_scenarios.py` | scenarios build and reach valid consensus |

Result: **96 passed** (`pytest -q`).

### Scenario results (mock mode)

| Scenario | Rounds | Violations | Sample | Hospitals | Dose | Power | Budget |
|---|---|---|---|---|---|---|---|
| baseline | 4 | 0 | 180 | 6 | 75 | 0.847 | $9.5M |
| budget_reduction | 5 | 0 | 180 | 5 | 75 | 0.847 | $9.0M |
| high_risk_drug | 5 | 0 | 210 | 12 | 50 | 0.815 | $11.7M |
| rare_disease | 5 | 0 | 190 | 13 | 75 | 0.848 | $14.5M |
| pediatric | 4 | 0 | 180 | 7 | 40 | 0.861 | $9.7M |
| pandemic | 4 | 0 | 180 | 7 | 75 | 0.847 | $10.5M |
| multi_country | 4 | 0 | 180 | 6 | 75 | 0.847 | $11.5M |
| unexpected_interim | 3 | 0 | 215 | 6 | 50 | 0.824 | $12.4M |

### Screenshots
See `docs/screenshots/`:
`01_baseline_round1.png`, `02_baseline_final.png`, `03_compare.png`, `04_pytest.png`, `05_high_risk.png`, `06_single_agent.png`; web UI: `ui_00_start.png`, `ui_01_negotiation.png`, `ui_02_protocol.png`, `ui_03_comparison.png`, `ui_04_audit.png`.

