"""Streamlit UI for the Multi-Agent Clinical Trial Protocol Negotiation system.

Run:  streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from main import run_multi_agent, run_single_agent
from scenarios import SCENARIOS, load_scenario

st.set_page_config(page_title="Clinical Trial Protocol Negotiation", layout="wide")

AGENT_LABEL = {"sponsor": "Sponsor", "biostatistician": "Biostatistician",
               "ethics_committee": "Ethics Committee", "patient_advocate": "Patient Advocate"}
DECISION_LABEL = {"APPROVE": "Approve", "REJECT": "Reject", "COUNTER_PROPOSE": "Counter-proposal"}
BLUE = "#1F5FA8"

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 1200px; }
    .stApp h1, [data-testid="stHeading"] h1 { color: #1F5FA8 !important; font-weight: 600 !important;
         font-size: 1.7rem !important; border-bottom: 2px solid #1F5FA8; padding-bottom: .4rem; }
    .stApp h2, .stApp h3 { color: #1B2A3A !important; font-weight: 600 !important; }
    [data-testid="stSidebar"] { background: #F3F7FC; border-right: 1px solid #D5E2F0; }
    [data-testid="stMetric"] { background: #FFFFFF; border: 1px solid #D5E2F0; border-radius: 4px;
                               padding: .6rem .8rem; }
    [data-testid="stMetricLabel"] { color: #4A5F78; }
    [data-testid="stMetricValue"] { font-size: 1.5rem; color: #1B2A3A; }
    [data-testid="stExpander"] { border: 1px solid #D5E2F0; border-radius: 4px; }
    .stTabs [aria-selected="true"] { color: #1F5FA8; }
    .note { background: #F3F7FC; border-left: 3px solid #1F5FA8; padding: .6rem .9rem; border-radius: 2px;
            color: #1B2A3A; margin: .5rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


def note(text: str) -> None:
    st.markdown(f'<div class="note">{text}</div>', unsafe_allow_html=True)

FIELDS = ["sample_size", "number_of_hospitals", "dosage", "dosage_arms", "trial_duration_months", "budget",
          "power", "hospital_visits", "invasive_procedures", "remote_monitoring", "randomization_scheme",
          "primary_endpoint"]

st.title("Multi-Agent Clinical Trial Protocol Negotiation")
st.caption("Four agents with private constraints negotiate one Phase II protocol. "
           "Academic simulation: all parameters are synthetic.")

with st.sidebar:
    st.header("Controls")
    key = st.selectbox("Scenario", list(SCENARIOS), format_func=lambda k: k.replace("_", " ").title())
    max_rounds = st.slider("Max rounds", 3, 15, 10)
    compare = st.checkbox("Also run single-agent baseline", value=True)
    run = st.button("Run negotiation", type="primary", width='stretch')
    scen = load_scenario(key)
    st.markdown(f"**{scen.title}**")
    st.write(scen.description)
    note(f"Research question: {scen.research_question}")

if run:
    # Nothing is written to disk from the UI (output_dir=None).
    st.session_state["mas"] = run_multi_agent(key, None, max_rounds, output_dir=None)
    st.session_state["single"] = run_single_agent(key, None, output_dir=None) if compare else None
    st.session_state["key"] = key

result = st.session_state.get("mas")
if result is None:
    note("Select a scenario in the sidebar and press <b>Run negotiation</b>.")
    st.stop()

single = st.session_state.get("single")
m = result.metrics

c = st.columns(5)
c[0].metric("Status", result.status.value.replace("_", " ").title())
c[1].metric("Rounds", m["rounds"])
c[2].metric("Constraint violations", m["constraint_violations"])
c[3].metric("Objections", m["objections_total"])
c[4].metric("Proposals accepted", f"{m['proposals_accepted'] + m['proposals_partially_accepted']}/{m['proposals_total']}")

tab_neg, tab_proto, tab_cmp, tab_audit = st.tabs(["Negotiation", "Protocol evolution", "Single vs multi-agent",
                                                  "Constraint audit"])

with tab_neg:
    for rnd in result.rounds:
        with st.expander(f"Round {rnd.round_number}  (protocol v{rnd.protocol_version}, "
                         f"{rnd.open_violations} open violations)", expanded=rnd.round_number == 1):
            for d in rnd.decisions:
                d = d.to_dict()
                who = AGENT_LABEL.get(d["agent"], d["agent"])
                st.markdown(f"**{who}** - {DECISION_LABEL.get(d['decision'], d['decision'])}")
                st.write(d["reason"])
                if d["proposed_changes"]:
                    st.code("; ".join(f"{k}={v}" for k, v in d["proposed_changes"].items()), language=None)
                if d["requests"]:
                    st.caption("Requests: " + "; ".join(f"{k}: {v}" for k, v in d["requests"].items()))
            if rnd.proposals:
                st.markdown("**Proposal outcomes**")
                for p in rnd.proposals:
                    p = p.to_dict()
                    st.write(f"- **{AGENT_LABEL.get(p['agent'], p['agent'])}**: {p['status']}")
                    if p.get("accepted_changes"):
                        st.caption("accepted: " + "; ".join(f"{k}={v}" for k, v in p["accepted_changes"].items()))
                    if p.get("rejected_changes"):
                        st.caption("blocked: " + "; ".join(f"{k}={v}" for k, v in p["rejected_changes"].items()))
                    for o in p.get("objections", []):
                        st.caption(f"objection - {o}")

with tab_proto:
    rows = []
    for rnd in result.rounds:
        after = rnd.protocol_after or result.final_protocol.to_dict()  # final round only approves
        row = {"after round": rnd.round_number}
        row.update({f: after.get(f) for f in FIELDS})
        rows.append(row)
    df = pd.DataFrame(rows)
    st.dataframe(df, width='stretch', hide_index=True)
    left, right = st.columns(2)
    with left:
        st.subheader("Power over rounds")
        st.line_chart(df.set_index("after round")["power"], color=BLUE)
    with right:
        st.subheader("Budget over rounds")
        st.line_chart(df.set_index("after round")["budget"], color=BLUE)
    st.subheader("Final protocol")
    st.json(result.final_protocol.to_dict())

with tab_cmp:
    if single is None:
        note("Enable the single-agent baseline in the sidebar to compare.")
    else:
        sp = single["final_protocol"]
        fp = result.final_protocol.to_dict()
        sp = sp if isinstance(sp, dict) else sp.to_dict()
        cmp = pd.DataFrame({"Multi-agent": {f: fp.get(f) for f in FIELDS},
                            "Single agent": {f: sp.get(f) for f in FIELDS}}).astype(str)
        st.dataframe(cmp, width='stretch')
        a, b = st.columns(2)
        a.metric("Multi-agent violations", m["constraint_violations"])
        b.metric("Single-agent violations", single["constraint_violations"])
        st.caption("The single-agent baseline is intentionally naive (one blended objective, no vetoes); it "
                   "illustrates silent trade-offs, not that no optimiser could satisfy the constraints.")
        for v in single["constraint_check"].get("violations", []):
            st.write(f"- {v['agent']}: {v['constraint']} (actual: {v['actual']})")

with tab_audit:
    check = result.constraint_check
    st.write("**Final protocol valid:**", check.get("valid"))
    if check.get("violations"):
        st.dataframe(pd.DataFrame(check["violations"]), width='stretch')
    else:
        note("Independent Constraint Checker found 0 violations.")
    if result.unresolved_conflicts:
        note("Unresolved conflicts")
        st.table(pd.DataFrame(result.unresolved_conflicts))
