
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
Command-line (`main.py`): `--mode`, `--scenario`, `--llm`, `--max-rounds`, `--no-transcript`, `--summary`, `--output-dir`, `--verbose`. Output: readable transcript + final result, saved to `outputs/`.

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
