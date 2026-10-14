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

| Section | Status | Present | Missing |
|---|---|---|---|
| **1. Introduction** | Present | README §1–3 (overview, problem, why multi-agent); case study `.md` | Nothing significant |
| **2. PEAS** | Present | README PEAS summary; `docs/rubric_docs.md` §A: detailed PEAS table, metric definitions with targets, per-agent input→sensor and output→actuator mapping | Nothing significant |
| **3. Agent & environment analysis** | Present | `docs/rubric_docs.md` §B: agent category (goal-based, utility-oriented, deliberative; mixed cooperative-competitive MAS) and full environment classification (observability, agents, determinism, episodic/sequential, static/dynamic, discrete/continuous, known/unknown) | Nothing significant |
| **4. Design** | Present | Architecture diagram, file table, workflow (README §4, §7, §8); `docs/rubric_docs.md` §C: algorithms used, hardware/software requirements, tool/package details, scalability | Nothing significant |
| **5. Implementation** | Present | Modules and sub-modules, mock/LLM modes, scenarios; `docs/rubric_docs.md` §D: input representation (`models.py` dataclasses), dataset note (synthetic scenarios, no patient data), UI (Streamlit `app.py` plus CLI `main.py`) | Nothing significant |
| **6. Testing & results** | Present | 7 test files; test levels table (unit / algorithm / integration / scenario); outputs for all 8 scenarios in `outputs/`; 6 screenshots in `docs/screenshots/` | Screenshots cover only baseline, compare, pytest, high-risk and single-agent runs (none for the other 5 scenarios); scenario figures and "96 passed" not re-verified by a fresh run |

## Other gaps

- **Q&A / presentation (1 mark):** `DEMO_AND_QA.md` covers the demo flow and likely questions; there are no finished slides in the folder (only `report/update_deck.py` and `report/build_deck.py.bak`).
- **Duplication:** the rubric documentation exists in both `docs/rubric_docs.md` and at the end of `README.md`; keep the two in sync.
- **Final report:** `report/Clinical_Trial_MAS_Report.docx` exists, but its content was not checked against the 6-section structure.

