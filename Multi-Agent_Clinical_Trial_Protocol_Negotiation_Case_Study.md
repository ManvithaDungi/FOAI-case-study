# FUNDAMENTALS OF ARTIFICIAL INTELLIGENCE — 23CSE401

## CASE STUDY REPORT

# Multi-Agent Clinical Trial Protocol Negotiation Using Autonomous AI Agents with Hidden Objectives

### A Multi-Agent System Design for Simulating Stakeholder Negotiation in Clinical Trial Protocol Development

**Submitted by**

- CB.SC.U4CSE23317 — Druva Teja Korlakunta
- CB.SC.U4CSE23318 — Manvitha Dungi

**July 2026**

---

## 1. Abstract

Designing a clinical trial protocol is an inherently collaborative and conflict-driven process that involves multiple stakeholders with distinct, often competing, priorities. Pharmaceutical sponsors seek to minimize cost and accelerate trial completion; biostatisticians focus on statistical validity; ethics committees prioritize participant safety; and patient advocates emphasize accessibility and reduced participant burden. Most existing AI systems treat protocol generation as a single optimization problem — collapsing these competing priorities into one blended objective and, in doing so, masking genuine disagreement between stakeholders.

This project proposes a Multi-Agent System (MAS) in which independent AI agents represent each stakeholder, each holding private objectives, private constraints, and specialized decision-making authority. Through structured negotiation, tool-assisted reasoning, and iterative protocol revision, the agents collaboratively converge on a single protocol that simultaneously satisfies regulatory, ethical, statistical, and operational requirements. This report presents the problem motivation, the justification for a multi-agent approach over a single-agent one, the agent and environment design, representative test scenarios, the intended tool stack, and the evaluation metrics that will be used once the system is implemented.

---

## 2. Problem Statement

Clinical trial protocol development today is a manual, iterative process that unfolds across meetings, document revisions, and negotiations among domain experts spanning several organizations. A single protocol must simultaneously satisfy a wide range of conflicting requirements, including:

- Conflicting stakeholder priorities (cost vs. safety vs. statistical rigor vs. patient burden)
- Hidden or private constraints that stakeholders do not openly disclose to one another
- Regulatory compliance obligations (FDA, EMA, ICH-GCP guidelines)
- Statistical validity requirements (power, significance, sample size)
- Ethical and participant-safety considerations
- Budget and timeline limitations
- Patient recruitment feasibility

Current AI assistants typically generate a protocol from a single prompt, producing one “averaged” answer that does not model genuine disagreement between stakeholders, does not expose the trade-offs being made, and offers no mechanism for a stakeholder to veto or renegotiate a term.

The objective of this project is to design a multi-agent negotiation framework that realistically simulates protocol development, so that a defined trial scenario can be given as input to the agent system and the resulting negotiation and output protocol can be evaluated.

---

## 3. Why This Problem Strictly Requires a Multi-Agent System

Each stakeholder in this domain differs from the others along several dimensions:

- **Different knowledge** — a biostatistician reasons about power and sample size; an ethics committee reasons about risk and consent.
- **Different authority** — some stakeholders can veto a protocol outright (IRB); others can only propose or object (Patient Advocate).
- **Different optimization goals** — minimizing cost is directly in tension with maximizing statistical power and minimizing risk.
- **Private information** — each party holds constraints (e.g., an absolute budget ceiling, or a maximum acceptable dosage) that are not shared openly with the others.
- **Independent decision-making** — each stakeholder decides and defends its own position rather than following a single shared reasoning chain.

A single agent, even if instructed to “consider all stakeholders,” collapses these into one internal reasoning chain and one blended objective. It cannot enforce information asymmetry (for example, the Sponsor should never see the Ethics Committee's absolute maximum-dosage limit), cannot represent a genuine veto, and cannot produce a transparent, per-stakeholder audit trail of who approved or rejected which change.

These properties are foundational to how real protocol review works in practice, and they can only be modeled faithfully with multiple independently-reasoning agents that each maintain their own private state and negotiate as separate entities.

---

## 4. Real-World Motivation and Existing Systems

Protocol development today genuinely involves multiple independent organizations, each of which reviews the protocol from its own perspective before granting approval:

- Pharmaceutical Sponsor
- Contract Research Organization (CRO)
- Institutional Review Board (IRB) / Ethics Committee
- Clinical Investigators
- Regulatory Agencies (FDA, EMA)
- Patient Advocacy Groups
- Biostatistics Team

This project reproduces that collaborative review workflow computationally. The systems below are described as being closest to this space; according to the report, none perform autonomous, hidden-objective, multi-party negotiation, which is the specific gap this project targets.

| System | What It Does | Gap This Project Addresses |
|---|---|---|
| Microsoft Healthcare AI | Clinical documentation and medical decision assistance | No autonomous multi-stakeholder negotiation |
| Medable | AI-enabled decentralized trial workflow automation | Automates workflow, not stakeholder conflict resolution |
| IQVIA Trial Design Platform | Protocol optimization using analytics | Single optimization objective, not multi-party negotiation |
| Medidata | AI-powered trial planning and analytics | Centralized planning, no private-objective agents |
| FDA Protocol Review Process | Human experts independently review submitted protocols | Manual and slow; not usable for rapid design testing |
| Meta CICERO | Multi-agent negotiation in Diplomacy under hidden intent | Strategy-game domain, not clinical trials |
| LLM Negotiation Benchmarks | Evaluate bargaining among LLM agents with conflicting goals | General-purpose; lacks domain-specific safety/statistical constraints |

---

## 5. Proposed Multi-Agent Environment

The environment simulates the collaborative development of a Phase II clinical trial protocol.

Each agent receives only partial information about the full problem:

- It knows the shared protocol draft.
- It knows only its own private objective and constraints.

Agents communicate through a structured negotiation protocol, collaboratively edit a shared protocol document, and the protocol is finalized only when every stakeholder agent approves it.

---

## 6. Agent Design

Four agents are defined, each representing one stakeholder role with its own objective, private constraints, and set of controllable decision variables.

| Agent | Objective | Private Constraints | Controlled Decisions |
|---|---|---|---|
| **Sponsor** | Complete the trial at minimum cost | Budget ≤ $15 million; Sample size ≤ 220; Trial duration ≤ 18 months | Sample size; Number of hospitals; Dosage arms; Budget allocation |
| **Biostatistician** | Ensure statistical validity of the trial | Power ≥ 80%; Alpha = 0.05; Sample size ≥ required minimum; Must avoid an underpowered study | Sample size; Randomization scheme; Endpoints; Statistical analysis plan |
| **Ethics Committee (IRB)** | Protect participant safety | Maximum allowable dosage; Exclusion criteria; Safety monitoring requirements; Adverse-event reporting rules | Safety limits; Monitoring frequency; Inclusion restrictions |
| **Patient Advocate** | Reduce participant burden | Maximum hospital visits; Wider eligibility criteria; Fewer invasive procedures; Preserve quality of life | Inclusion criteria; Visit schedule; Patient burden constraints |

---

## 7. Shared Environment State

The environment maintains a shared state that every agent can read:

- Current protocol draft
- Negotiation history / transcript
- Regulatory reference documents
- Clinical guidelines
- Trial budget
- Study timeline

It also maintains a private state that only the owning agent can read.

Only the owning agent can read its own private objective and constraints. This asymmetry between shared, publicly visible state and per-agent private state is the core mechanism that makes genuine multi-agent negotiation possible, and it is precisely what a single-agent design cannot represent.

---

## 8. System Workflow

Each negotiation run follows a fixed sequence of steps:

1. **Initialize the scenario** — select a test case, e.g., a budget cut or a rare-disease trial.
2. **Assign hidden objectives and private constraints** to each agent.
3. **Initialize agents** with role-specific system prompts and tool access.
4. **Sponsor agent proposes** an initial protocol draft.
5. **Biostatistician, IRB, and Patient Advocate agents** review the draft independently.
6. **Agents negotiate** by proposing amendments, arguing for their position, and accepting or rejecting changes.
7. **Update the shared protocol document** after each accepted change.
8. **Constraint Checker validates** the updated draft against all hard constraints.
9. **Repeat Steps 4–8** until every agent approves (consensus) or a round limit is reached.
10. **Output** either:
   - An approved protocol and full negotiation transcript, or
   - A report of unresolved conflicts.

---

## 9. Example Negotiation Walkthrough

The following abridged transcript illustrates a single negotiation round on the baseline scenario.

### Sponsor
Proposes reducing the sample size from 320 to 180 to cut cost.

### Biostatistician
Reports that statistical power falls to 63% at that sample size and rejects the change.

### IRB
Will accept a reduced sample size only if the trial dosage is also reduced.

### Patient Advocate
Requests fewer required hospital visits to lower participant burden.

### Sponsor
Counter-proposes increasing remote monitoring to offset the reduced visit count.

### Consensus

Consensus is reached once all four agents approve the revised draft:

- A moderately reduced sample size that still clears the power threshold
- A lowered dosage
- A visit schedule supplemented by remote monitoring

---

## 10. Additional Scenarios

Beyond the baseline walkthrough above, the following seven scenarios will be used as fixed test inputs to the agent system once implemented. Each scenario changes the starting conditions of the same environment, producing a different negotiation dynamic and a different research question to evaluate.

| Scenario | Setup | Key Research Question |
|---|---|---|
| **1. Budget Reduction** | Trial budget cut by 40% | Can the agents still converge on a statistically valid, safe protocol under a tight cost constraint? |
| **2. High-Risk Drug** | Drug has severe known side effects; Sponsor wants fast approval | Does the IRB successfully resist an accelerated, higher-risk timeline? |
| **3. Rare Disease** | Eligible patient population is very small | Can the Patient Advocate's push for relaxed eligibility be reconciled with the minimum sample size the Biostatistician requires? |
| **4. Pediatric Trial** | Participants are minors | Do added ethical constraints and a stricter Patient Advocate still allow the agents to converge? |
| **5. Pandemic Trial** | Urgent public-health need for rapid approval | Does the system preserve safety standards under strong time pressure? |
| **6. Multi-Country Trial** | Different countries impose different regulatory requirements | Can the agents negotiate a single protocol that is compliant across all jurisdictions at once? |
| **7. Unexpected Interim Results** | Interim analysis reveals unexpected adverse events mid-trial | Can the agents renegotiate dosage, sample size, and monitoring without invalidating prior statistical assumptions? |

For each scenario, a fixed input (trial description, budget, and drug profile) will be given to the agent system, and outputs such as the final protocol, number of negotiation rounds, and constraint violations will be logged for later comparison across scenarios and against a single-agent baseline.

Running these simulations and analyzing results is planned for the next phase of the project and is outside the scope of this design report.

---

## 11. Why a Single Agent Cannot Solve This

| Single Agent | Multi-Agent System |
|---|---|
| Optimizes one blended objective | Maintains independent, per-stakeholder objectives |
| No hidden information | Hidden / private constraints are preserved per agent |
| No genuine disagreement | Explicit negotiation and conflict resolution |
| One reasoning chain | Multiple specialized, independent reasoning processes |
| Limited transparency | Traceable decisions and positions from each stakeholder |
| Can silently overlook minority concerns | Every stakeholder can approve or veto a proposal |

---

## Source Note

This Markdown document was converted from the uploaded case study report:

**“Multi-Agent Clinical Trial Protocol Negotiation Using Autonomous AI Agents with Hidden Objectives”**, *Fundamentals of Artificial Intelligence — 23CSE401*, July 2026. The source report is 5 pages and contains the sections, tables, and negotiation walkthrough represented above. fileciteturn0file0L2-L11
