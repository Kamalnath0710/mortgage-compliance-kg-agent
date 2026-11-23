from datetime import date
import pandas as pd
import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Mortgage Compliance KG-RAG Prototype", layout="wide")
st.title("U.S. Mortgage Compliance Engine — Local Ollama + KG-RAG Prototype")

# Sidebar: Part A Offline Knowledge Pipeline
with st.sidebar:
    st.header("Part A: Offline Knowledge Pipeline")
    st.caption("Stages 1 → 2A/2B → 3 (Qdrant + NetworkX KG + SQLite)")
    if st.button("1. Run Regulatory Ingestion", type="primary", use_container_width=True):
        with st.spinner("Ingesting Fannie Mae & Overlay guidelines into Qdrant + KG..."):
            res = requests.post(f"{API_BASE}/ingest", timeout=60).json()
            st.success("Ingestion Complete!")
            st.json(res["stats"])

    st.divider()
    st.header("Load Test Scenario")
    scenario = st.selectbox(
        "Select Loan Test Case",
        [
            "Scenario 1: Fail due to Lender Overlay (DTI 47.5% > 45% Cap)",
            "Scenario 2: Pass All Guidelines (DTI 38%, FICO 740, LTV 80%)",
            "Scenario 3: Insufficient Evidence (Missing Reserves when LTV > 80% & DTI > 40%)",
        ],
    )

# Preset values based on selected scenario
if "Scenario 1" in scenario:
    defaults = dict(loan_id="LN-2025-8841", app_date=date(2025, 3, 10), fico=725, income=8000.0, debt=3800.0, loan_amt=360000.0, val=450000.0, reserves=3.0, include_res=True)
elif "Scenario 2" in scenario:
    defaults = dict(loan_id="LN-2025-8842", app_date=date(2025, 3, 12), fico=740, income=10000.0, debt=3800.0, loan_amt=320000.0, val=400000.0, reserves=4.0, include_res=True)
else:
    defaults = dict(loan_id="LN-2025-8843", app_date=date(2025, 3, 15), fico=690, income=9000.0, debt=3870.0, loan_amt=360000.0, val=400000.0, reserves=0.0, include_res=False)

st.subheader("Stage 4: Case / Loan Payload & Evidence Intake")
c1, c2, c3, c4 = st.columns(4)
with c1:
    loan_id = st.text_input("Loan ID", defaults["loan_id"])
    app_date = st.date_input("Application Date", defaults["app_date"])
with c2:
    fico = st.number_input("Representative FICO", value=defaults["fico"], step=5)
    aus = st.selectbox("AUS Finding", ["Approve/Eligible", "Manual"])
with c3:
    income = st.number_input("Gross Monthly Income ($)", value=defaults["income"], step=250.0)
    debt = st.number_input("Monthly Debt Obligations ($)", value=defaults["debt"], step=100.0)
with c4:
    loan_amt = st.number_input("Loan Amount ($)", value=defaults["loan_amt"], step=5000.0)
    appraised_val = st.number_input("Appraised Value ($)", value=defaults["val"], step=5000.0)

include_reserves = st.checkbox("Include Liquid Reserves Verification", value=defaults["include_res"])
reserves_val = st.number_input("Liquid Reserves (Months)", value=defaults["reserves"], step=0.5, disabled=not include_reserves)

if st.button("Run Stage 5 → 9 Compliance Evaluation", type="primary"):
    payload = {
        "loan_id": loan_id,
        "agency": "Fannie Mae",
        "program": "Conventional",
        "application_date": app_date.isoformat(),
        "occupancy": "Primary Residence",
        "property_type": "Single Family",
        "credit_score": {"value": fico, "source_doc": "Equifax_TriMerge.pdf", "page": 1},
        "gross_monthly_income": {"value": income, "source_doc": "W2_and_Paystub.pdf", "page": 2},
        "monthly_debt_obligations": {"value": debt, "source_doc": "1003_URLA.pdf", "page": 4},
        "loan_amount": {"value": loan_amt, "source_doc": "1003_URLA.pdf", "page": 1},
        "appraised_value": {"value": appraised_val, "source_doc": "1004_Appraisal.pdf", "page": 3},
        "liquid_reserves_months": (
            {"value": reserves_val, "source_doc": "Bank_Statement.pdf", "page": 1}
            if include_reserves
            else None
        ),
        "aus_recommendation": {"value": aus, "source_doc": "DU_Findings.pdf", "page": 1},
    }

    with st.spinner("Running Temporal Hybrid Retrieval, Deterministic Rule Engine & Ollama Agents..."):
        resp = requests.post(f"{API_BASE}/evaluate", json=payload, timeout=300)
        if resp.status_code != 200:
            st.error(f"Error: {resp.text}")
        else:
            result = resp.json()
            st.session_state["last_result"] = result

if "last_result" in st.session_state:
    res = st.session_state["last_result"]
    st.divider()

    # Stage 8 Banner
    st.subheader(f"Stage 8: Auditable Final Assessment — `{res['status']}` (Audit ID: `{res['audit_id']}`)")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Stage 5: Temporal Filter & Precedence Resolution**")
        st.write("Superseded / Future Rules Filtered Out:", res["superseded_rules_filtered"])
        st.write("Overlay Precedence Overrides Applied:", res["overlay_overrides_applied"])
    with col_b:
        st.markdown("**Stage 7B: Citation & Grounding Verification**")
        st.write(f"Citation Check Passed: `{res['citation_verification_passed']}` | Re-query Loop Triggered: `{res['requery_triggered']}`")
        for cit in res["verified_citations"]:
            st.info(f"**[{cit['section_id']}]**: \"{cit['quote']}\"")

    st.markdown("**Stage 6: Deterministic Compliance Rule Engine Traces (Computed Before LLM)**")
    df_traces = pd.DataFrame(res["deterministic_traces"])
    st.dataframe(df_traces, use_container_width=True)

    st.markdown("**Stage 7A: Ollama Reasoning Agent Synthesis**")
    st.write(res["reasoning_summary"])

    # Stage 9 HITL Override
    st.divider()
    st.subheader("Stage 9: HITL Review Queue & Immutable Audit Log")
    with st.form("hitl_form"):
        h1, h2, h3 = st.columns([1, 1, 2])
        override_status = h1.selectbox("Underwriter Decision", ["Approve Exception", "Confirm Fail", "Request Conditions"])
        reviewer = h2.text_input("Underwriter Name", "Senior Underwriter")
        notes = h3.text_input("Compensating Factors / Audit Rationale", "Verified 12-month cash reserves compensating factor.")
        if st.form_submit_button("Record HITL Audit Decision"):
            requests.post(
                f"{API_BASE}/hitl-override",
                json={
                    "audit_id": res["audit_id"],
                    "override_status": override_status,
                    "reviewer_name": reviewer,
                    "notes": notes,
                },
            )
            st.success(f"Recorded immutable HITL audit decision for {res['audit_id']}")