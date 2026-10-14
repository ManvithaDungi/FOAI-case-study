from docx import Document
from docx.shared import Pt, Inches

D = Document()
st = D.styles['Normal']
st.font.name = 'Calibri'
st.font.size = Pt(11)


def H(t, l=1):
    D.add_heading(t, l)


def P(t):
    D.add_paragraph(t)


def B(items):
    for i in items:
        D.add_paragraph(i, style='List Bullet')


def T(rows):
    t = D.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = 'Table Grid'
    for i, r in enumerate(rows):
        for j, c in enumerate(r):
            cell = t.cell(i, j)
            cell.text = str(c)
            if i == 0:
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.bold = True
    D.add_paragraph()


def IMG(f, cap):
    D.add_picture('report/screens/' + f, width=Inches(6.2))
    P(cap)


D.add_heading('Multi-Agent Clinical Trial Protocol Negotiation', 0)
P('Fundamentals of Artificial Intelligence (23CSE401) - Case Study, Review 1\n'
  'CB.SC.U4CSE23317 - Druva Teja Korlakunta\nCB.SC.U4CSE23318 - Manvitha Dungi')

H('1. Introduction')
P('Designing a clinical trial protocol is a negotiation between stakeholders with conflicting goals and undisclosed '
  'limits: the Sponsor wants minimum cost and time, the Biostatistician wants statistical validity, the Ethics '
  'Committee (IRB) wants participant safety, and the Patient Advocate wants low burden and wide access. A '
  'single-prompt AI system collapses these into one blended answer, hides trade-offs, offers no veto and needs '
  'every confidential limit in one place.')
P('This project implements a Multi-Agent System (MAS) in which four autonomous agents, each holding private '
  'objectives and constraints, negotiate one shared Phase II protocol over several rounds. An independent '
  'Constraint Checker audits every protocol version. The protocol is final only when all four agents approve. '
  'The system runs deterministically in mock mode (no API key) and optionally with an LLM. All data is '
  'synthetic; this is an academic simulation only.')
P('Contributions: (i) a four-agent negotiation engine with enforced information asymmetry, IRB veto and advisory '
  'Patient Advocate; (ii) eight test scenarios; (iii) a single-agent baseline for comparison; (iv) a 96-test '
  'automated suite.')

H('2. PEAS Description')
T([['Component', 'Description'],
   ['Performance measure', 'Consensus reached (all 4 approve); constraint violations = 0 (independent checker); '
    'number of rounds; proposals accepted / partially accepted / rejected; objections raised; field changes '
    'accepted vs blocked; protocol validity (power >= 0.80, cost <= budget, safety limits)'],
   ['Environment', 'Shared Phase II protocol document, negotiation history, guidelines, budget, timeline and '
    'public calculators (power, sample size, cost, recruitment); plus per-agent private state'],
   ['Actuators', 'APPROVE / REJECT / COUNTER_PROPOSE decisions; amendments to the agent\'s own protocol fields; '
    'qualitative requests (e.g. hospital_visits: decrease); objections with reasons'],
   ['Sensors', 'Current protocol version, public negotiation history, public tool report (power, cost, '
    'recruitment), feedback on own proposals, own private constraints']])
H('Performance metric definitions', 2)
T([['Metric', 'Definition', 'Target'],
   ['Consensus', 'All four agents APPROVE the same protocol version', 'Yes'],
   ['Constraint violations', 'Hard-constraint failures reported by ConstraintChecker on the final protocol', '0'],
   ['Rounds', 'Negotiation rounds until consensus (max 10)', 'Low'],
   ['Proposal acceptance', '(accepted + partially accepted) / total proposals', 'High'],
   ['Objections', 'Blocking objections raised by other agents', 'Informational'],
   ['Power', 'Statistical power of final design', '>= 0.80'],
   ['Cost', 'Estimated cost vs budget ceiling', '<= budget']])
H('Input -> sensor and output -> actuator mapping', 2)
T([['Agent', 'Inputs (sensors)', 'Outputs (actuators)'],
   ['Sponsor', 'Shared protocol, public power/cost/recruitment report, feedback on blocked proposals, own '
    'budget / sample / duration limits', 'sample_size, number_of_hospitals, dosage_arms, budget, duration, '
    'remote_monitoring; requests to reduce visits/procedures'],
   ['Biostatistician', 'Shared protocol, public power report, own power/alpha thresholds and locked fields',
    'sample_size, randomization_scheme, primary_endpoint, alpha'],
   ['Ethics Committee', 'Shared protocol, own max dose, monitoring and AE-reporting rules',
    'dosage, safety_monitoring, adverse_event_reporting, exclusion/consent criteria (binding veto)'],
   ['Patient Advocate', 'Shared protocol, own max visits / invasive procedures / exclusions',
    'inclusion_criteria, hospital_visits, invasive_procedures, request for remote monitoring (advisory)']])

H('3. Agent and Environment Analysis')
H('Agent category', 2)
P('Each agent is a goal-based, utility-oriented rational agent with a model of the shared protocol. Agents are '
  'deliberative (they reason over the current protocol and their constraints rather than reacting to a single '
  'percept) and the Sponsor additionally has a simple learning component: when a sample-size cut is blocked it '
  'records the power of the blocked design and proposes a higher sample next time, inferring the hidden power '
  'threshold. Overall the system is a mixed cooperative-competitive multi-agent system with heterogeneous '
  'authority (IRB veto, advisory Patient Advocate).')
H('Environment classification', 2)
T([['Property', 'Classification', 'Justification'],
   ['Observability', 'Partially observable', 'Agents see the shared protocol but not each other\'s private '
    'constraints'],
   ['Agents', 'Multi-agent (mixed cooperative/competitive)', 'Four stakeholders with conflicting goals that '
    'must still reach joint agreement'],
   ['Determinism', 'Deterministic (mock mode); stochastic in LLM mode', 'Same input gives same negotiation in '
    'mock mode'],
   ['Episodicity', 'Sequential', 'Each round builds on the previous protocol version'],
   ['Static/Dynamic', 'Static between rounds, changes across rounds', 'Protocol changes only through accepted '
    'amendments; unexpected_interim changes constraints mid-trial'],
   ['Discrete/Continuous', 'Discrete time (rounds), mixed variables', 'Sample size and visits are integers; '
    'dosage and budget are bounded numeric values'],
   ['Known/Unknown', 'Known rules, hidden peer constraints', 'Power/cost models are public; peers\' limits '
    'are hidden']])

H('4. Design')
H('System architecture', 2)
P('Environment (shared protocol + guarded private states) -> four agents -> Negotiation Engine (reviews, '
  'proposals, objections) -> Constraint Checker (audit log) -> Consensus / Deadlock / No consensus. Only the '
  'Constraint Checker holds all constraints, and its detailed output goes to the audit log, not to the agents.')
T([['Module', 'Role'],
   ['environment.py', 'ClinicalTrialEnvironment, SharedState; raises PrivateStateAccessError on cross-agent '
    'access'],
   ['agents.py', 'Agent base class + Sponsor, Biostatistician, Ethics, PatientAdvocate agents; mock and LLM '
    'review; sanitize()'],
   ['negotiation.py', 'NegotiationEngine: round loop, proposal processing, deadlock detection'],
   ['constraints.py', 'Per-role hard-constraint checks and ConstraintChecker'],
   ['trial_tools.py', 'Public calculators: power, required sample size, cost, recruitment'],
   ['scenarios.py', 'Baseline + 7 scenarios'],
   ['single_agent.py', 'Single-agent baseline for comparison'],
   ['llm.py / config.py', 'OpenAI-compatible client (stdlib urllib) and .env settings'],
   ['logger.py / main.py', 'JSON-lines event log, reports, CLI']])
H('Algorithms used', 2)
B(['Round-based iterative negotiation: all agents review the same protocol snapshot independently, then propose '
   'amendments.',
   'Priority-ordered proposal processing (IRB -> Sponsor -> Biostatistician -> Patient Advocate); IRB safety '
   'amendments are binding, Patient Advocate objections are advisory.',
   'Proposal evaluation: each other agent checks the amended copy against its own hard constraints; a blocking '
   'objection rejects the change.',
   'Field-by-field retry: a blocked multi-field proposal is split so compatible parts survive (partial '
   'acceptance).',
   'Sponsor concession learning: uses the public power of blocked designs to propose a feasible sample size.',
   'Termination: consensus, deadlock (protocol unchanged for two rounds) or max_rounds (default 10).',
   'Deterministic rule-based strategies in mock mode; LLM mode adds JSON-validated reasoning with fallback and '
   'a guard that overrides an APPROVE violating the agent\'s own constraints.'])
H('Hardware and software requirements', 2)
T([['Item', 'Requirement'],
   ['Hardware', 'Any standard PC/laptop, >= 4 GB RAM, no GPU; network only for optional LLM mode'],
   ['OS', 'Windows / Linux / macOS'],
   ['Language', 'Python 3.10+ (tested on 3.10.11)'],
   ['Runtime libraries', 'Standard library only (urllib, dataclasses, argparse, json)'],
   ['Test library', 'pytest'],
   ['Optional', 'OpenAI-compatible API key, or local Ollama / LM Studio, for --llm']])
H('Tool / package details', 2)
T([['Tool', 'Purpose'],
   ['Python standard library', 'Core implementation, dataclasses for state, argparse CLI, json logging'],
   ['pytest', 'Automated unit / integration / scenario tests'],
   ['config.py (.env loader)', 'API key and model configuration'],
   ['OpenAI-compatible HTTP API (optional)', 'LLM reasoning per agent from role prompt files in prompts/']])

H('5. Implementation')
H('Input representation', 2)
P('The protocol is a Protocol dataclass (models.py) with fields: sample_size, number_of_hospitals, dosage, '
  'dosage_arms, trial_duration_months, budget, power, alpha, randomization_scheme, primary_endpoint, '
  'hospital_visits, remote_monitoring, invasive_procedures, inclusion_criteria, exclusion_criteria, '
  'safety_monitoring, adverse_event_reporting. Each agent has a PrivateState of numeric/enumerated limits. '
  'Decisions are AgentDecision objects, amendments are Proposal objects and each round is a NegotiationRound. '
  'A scenario is a named set of initial protocol, trial context and private states.')
H('Dataset description', 2)
P('The scenarios are synthetic, defined in scenarios.py with the starting values of the case-study report '
  '(320 patients, Sponsor cap 220 and target 180, 10 hospitals, 2 dose arms, 18 months). They are validated against '
  'real data: 5,000 completed Phase II interventional trials fetched from the ClinicalTrials.gov API v2 '
  '(fetch_real_data.py, accessed 2026-10-14). Position of the starting values in the real distribution: 320 patients '
  '= 92nd percentile, cap 220 = 88th, target 180 = 83rd, 10 hospitals = 54th percentile of multi-site trials, '
  '18 months = 29th percentile; 2 arms is the real median. Real medians: enrolment 56 (IQR 29-122), duration 32 '
  'months (IQR 16-57). The baseline is therefore a deliberately large, expensive Phase II draft, and its final '
  'protocol of 180 patients is still above the real 80th percentile. Cost per patient, dose-response and '
  'constraint thresholds are not recorded in the registry and remain synthetic. No patient-level data is used.')
H('Modules and sub-modules', 2)
B(['Environment: shared state, guarded private state, protocol versioning.',
   'Agents: review_protocol, evaluate_proposal (self-check), sanitize (redacts private numbers), mock and LLM '
   'strategies.',
   'Negotiation: round loop, proposal processing, partial acceptance, deadlock/max-round detection.',
   'Constraints: check_sponsor / check_biostatistician / check_ethics / check_patient_advocate / check_all.',
   'Tools: power, required sample size, cost, recruitment calculators.',
   'Scenarios: baseline, budget_reduction, high_risk_drug, rare_disease, pediatric, pandemic, multi_country, '
   'unexpected_interim.',
   'Baseline: single_agent.py with blended weights (cost 0.35, power 0.25, safety 0.20, burden 0.20).',
   'Logging: transcript .txt, result .json, event .jsonl per scenario in outputs/.'])
H('User interface', 2)
P('Web UI (streamlit run app.py): scenario picker, round-by-round negotiation, protocol evolution charts, single-vs-multi-agent comparison and constraint audit (Figures 7-10). Command-line interface (main.py): --mode {multi-agent,baseline,compare}, --scenario {name|all}, --llm, '
  '--max-rounds, --no-transcript, --summary, --output-dir, --verbose. Results are shown as a readable '
  'transcript and final-result summary and saved to outputs/.')
H('Scalability and code structure', 2)
P('One module per concern; a new agent needs an Agent subclass, a prompt file, a PrivateState and a constraint check; a new scenario is one entry in scenarios.py; the LLM backend is swappable via OPENAI_BASE_URL. Private state isolation means new stakeholders (CRO, regulator) do not change existing agents.')
H('Information asymmetry', 2)
B(['Private state is stored in the environment; get_private_state raises PrivateStateAccessError unless the '
   'requester is the owner.',
   'Each agent is constructed with only its own PrivateState; LLM prompts never include other agents\' '
   'constraints (tested).',
   'Public messages are qualitative ("dosage exceeds my safety requirements", not "max 75 mg").'])

H('6. Testing and Results')
H('Levels of testing', 2)
T([['Level', 'File', 'Tests', 'What is verified'],
   ['Unit - tools', 'test_trial_tools.py', '13', 'Power, sample size, cost, recruitment calculations'],
   ['Unit - constraints', 'test_constraints.py', '10', 'Per-role violations and ConstraintChecker'],
   ['Unit - models/utils', 'test_models.py, test_utils.py', '17', 'Dataclasses, serialisation, helpers'],
   ['Algorithm', 'test_negotiation_algorithm.py', '12', 'Authority order, partial acceptance, deadlock, '
    'max rounds'],
   ['Integration', 'test_mas.py', '18', 'Private-state guard, no leakage into prompts, LLM validation / '
    'fallback, end-to-end runs'],
   ['Scenario', 'test_scenarios.py', '12', 'Scenario construction and valid consensus'],
   ['Total', '', '82 test functions (96 cases incl. parametrised)', 'pytest: 96 passed in 9.6 s']])
H('Scenario results (mock mode)', 2)
T([['Scenario', 'Status', 'Rounds', 'Proposals', 'Objections', 'Violations', 'Sample', 'Dose (mg)', 'Power',
    'Budget ($M)', 'Visits'],
   ['baseline', 'CONSENSUS', '4', '9', '5', '0', '180', '75', '0.847', '9.5', '4'],
   ['budget_reduction', 'CONSENSUS', '5', '9', '5', '0', '180', '75', '0.847', '9.0', '4'],
   ['high_risk_drug', 'CONSENSUS', '5', '10', '7', '0', '210', '50', '0.815', '11.7', '4'],
   ['rare_disease', 'CONSENSUS', '5', '9', '6', '0', '190', '75', '0.848', '14.5', '6'],
   ['pediatric', 'CONSENSUS', '4', '9', '6', '0', '180', '40', '0.861', '9.7', '3'],
   ['pandemic', 'CONSENSUS', '4', '9', '5', '0', '180', '75', '0.847', '10.5', '6'],
   ['multi_country', 'CONSENSUS', '4', '9', '5', '0', '180', '75', '0.847', '11.5', '4'],
   ['unexpected_interim', 'CONSENSUS', '3', '3', '1', '0', '215', '50', '0.824', '12.4', '6']])
H('Multi-agent vs single-agent baseline', 2)
T([['Scenario', 'MAS rounds', 'MAS violations', 'Single-agent violations'],
   ['baseline', '4', '0', '7'], ['budget_reduction', '5', '0', '8'], ['high_risk_drug', '5', '0', '9'],
   ['rare_disease', '5', '0', '7'], ['pediatric', '4', '0', '10'], ['pandemic', '4', '0', '8'],
   ['multi_country', '4', '0', '8'], ['unexpected_interim', '3', '0', '4']])
P('Discussion: in the baseline scenario the Sponsor cut from 320 to 180 patients is blocked by the '
  'Biostatistician because power would fall to about 0.64; the IRB lowers the dosage to 75 mg and tightens '
  'exclusions; the Patient Advocate visit reduction is accepted only once the Sponsor funds remote monitoring. The '
  'final protocol has power 0.847 and zero violations. The single-agent baseline, given all constraints in one '
  'place, still produced 4-10 violations because trade-offs are soft penalties with no veto. The baseline is '
  'intentionally naive, so this shows the effect of silent trade-offs, not that a well-engineered optimiser could '
  'never satisfy the constraints.')
P('Limitations: synthetic simplified models, hand-written mock strategies, deterministic proposal evaluation '
  'even in LLM mode, fixed processing order, best-effort redaction of private numbers.')
H('Simulation screenshots', 2)
IMG('01_baseline_round1.png', 'Figure 1: Baseline scenario, Round 1 negotiation transcript.')
IMG('02_baseline_final.png', 'Figure 2: Baseline final result - CONSENSUS, 4 rounds, 0 violations.')
IMG('05_high_risk.png', 'Figure 3: High-risk drug scenario - dosage held at 50 mg, duration 12 months.')
IMG('03_compare.png', 'Figure 4: Multi-agent vs single-agent comparison across all scenarios.')
IMG('06_single_agent.png', 'Figure 5: Single-agent baseline output with constraint violations.')
IMG('04_pytest.png', 'Figure 6: Automated test run - 96 passed.')
IMG('ui_01_negotiation.png', 'Figure 7: Web UI - negotiation view with per-round agent decisions.')
IMG('ui_02_protocol.png', 'Figure 8: Web UI - protocol evolution table and power / budget charts.')
IMG('ui_03_comparison.png', 'Figure 9: Web UI - multi-agent vs single-agent comparison.')
IMG('ui_04_audit.png', 'Figure 10: Web UI - independent constraint audit.')

D.save('report/Clinical_Trial_MAS_Report.docx')

