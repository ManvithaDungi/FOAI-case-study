# Rubrics

## Review 1: 20 Marks

| Criterion                                     | Marks |
| --------------------------------------------- | :---: |
| PEAS Formulation                              |   3   |
| Environment & Agent Analysis                  |   3   |
| Algorithmic Modeling & Search Strategy        |   3   |
| Q&A & Presentation Mechanics                  |   1   |
| Tool/Package Selection & Setup                |   3   |
| Multi-Agent Execution & Interaction           |   3   |
| Demo Quality & Testing Scenarios              |   3   |
| Code Structure & Scalability                  |   1   |
| **Total**                                     | **20** |

---

## Report Structure

### 1. Introduction

- Provide an introduction to your multi-agent system.

### 2. PEAS Description

- Add the PEAS description.
- Ensure that performance metrics are properly defined.
- Identify actuators and sensors.
- Specify the input-sensor mapping as well as the output-actuator mapping.

### 3. Agent and Environment Analysis

- Describe your agent category.
- Provide a complete classification of your environment.

### 4. Design

Describe:

- System architecture
- Algorithms used
- Hardware and software requirements
- Tool/package details
- Any other details relevant to system design

### 5. Implementation

Provide a summary of the implementation, including:

- Input representation
- Dataset description (if you are using one)
- Modules and sub-modules
- User interface
- Other details relevant to your implementation and simulation

### 6. Testing and Results

- Discuss the test cases used and the levels of testing carried out.
- Include a few simulation/demo screenshots.


Let me read the key documents.

Short answer: **the code and design content is almost all there, but the report itself isn't written, and a few rubric items are only implicit.** Nothing in the folder is a report in your 6-section structure; the README and case-study `.md` hold the raw material.

## Rubric report sections

| Section | Status | Where |
|---|---|---|
| **1. Introduction** | Present (raw material) | Case study `.md` §1–5; README §1–3 |
| **2. PEAS** | Partial | README has a 4-row PEAS table. **Missing:** explicit performance metric definitions, and an explicit *input→sensor* and *output→actuator* mapping (the table lists them but doesn't map them) |
| **3. Agent & environment analysis** | Partial | The environment is described in one line ("partially observable, multi-agent, sequential, deterministic in mock mode"). **Missing:** the *agent category* (goal-based / utility-based / learning, etc.) is never stated, and there's no full classification (static vs dynamic, discrete vs continuous, known vs unknown, episodic vs sequential, competitive vs cooperative) |
| **4. Design** | Mostly present | Architecture diagram, file table, workflow (README §4, §7, §8). **Missing:** hardware/software requirements section (only install steps), and no explicit "algorithms used" statement (e.g. rule-based negotiation, priority-ordered proposal evaluation, field-by-field fallback) |
| **5. Implementation** | Mostly present | Modules, mock/LLM modes, CLI, scenarios. **Missing:** "input representation" described as such (dataclasses are in `models.py`, not explained), and a **dataset** note (it's synthetic scenarios; say so explicitly). The "UI" is CLI-only |
| **6. Testing & results** | Partial | 7 test files, outputs for scenarios, compare table. **Missing:** a written discussion of test levels (unit / integration / scenario), and **screenshots**; none exist in the folder |

## Other gaps

- **Outputs are incomplete.** Only `baseline`, `budget_reduction`, `high_risk_drug`, `pediatric` are in `outputs/`. `rare_disease`, `pandemic`, `multi_country`, `unexpected_interim` have no saved results, though the README table claims results for all eight.
- **Q&A / presentation (1 mark):** no slides or demo script.
- **README mentions `scenarios.py` "baseline + 7"**, which matches the case study, so that's consistent.
- Some README numbers (e.g. `compare` table, power 0.847) should be re-verified by running the code before you cite them in the report.

