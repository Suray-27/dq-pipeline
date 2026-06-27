import streamlit as st
import pandas as pd
import sqlalchemy
import os
import json
import plotly.express as px
from dotenv import load_dotenv
load_dotenv()

DB_URL = os.environ.get("DB_URL_VAR")


@st.cache_resource
def get_engine():
    return sqlalchemy.create_engine(DB_URL)


@st.cache_data(ttl=300)
def load_table(table_name):
    engine = get_engine()
    return pd.read_sql(f"SELECT * FROM {table_name}", engine)


def safe_load(table_name):
    try:
        return load_table(table_name)
    except Exception:
        return pd.DataFrame()


# ─── Page Config ───────────────────────────────────────────────
st.set_page_config(
    page_title="AI Data Quality Dashboard",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 AI Data Quality Pipeline")
st.caption("Powered by Groq LLM · Qwen3 Root Cause · Neon PostgreSQL")

# ─── Load All Tables ───────────────────────────────────────────
curated_customers = safe_load("curated_customers")
quarantine_customers = safe_load("quarantine_customers")
curated_transactions = safe_load("curated_transactions")
quarantine_transactions = safe_load("quarantine_transactions")
violations = safe_load("dq_violations")
fixes = safe_load("dq_fix_suggestions")
summaries = safe_load("dq_run_summaries")
lineage = safe_load("data_lineage")
drift = safe_load("dq_drift_reports")
rca = safe_load("dq_root_cause_analysis")

# ─── Top Metrics ───────────────────────────────────────────────
st.subheader("📊 Pipeline Summary")

total_curated = len(curated_customers) + len(curated_transactions)
total_quarantine = len(quarantine_customers) + len(quarantine_transactions)
total = total_curated + total_quarantine
pass_rate = round(total_curated / total * 100, 1) if total > 0 else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("✅ Total Curated", total_curated)
col2.metric("🚫 Total Quarantined", total_quarantine)
col3.metric("⚠️ Violations", len(violations))
col4.metric("📈 Pass Rate", f"{pass_rate}%")
col5.metric("🔄 Tables Processed", 2)

st.divider()

# ─── Per Table Summary ─────────────────────────────────────────
st.subheader("📋 Per Table Summary")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**👥 Customers**")
    c1, c2, c3 = st.columns(3)
    c1.metric("Curated", len(curated_customers))
    c2.metric("Quarantined", len(quarantine_customers))
    total_c = len(curated_customers) + len(quarantine_customers)
    c3.metric("Pass Rate", f"{round(len(curated_customers)/total_c*100, 1) if total_c > 0 else 0}%")

with col2:
    st.markdown("**💳 Transactions**")
    c1, c2, c3 = st.columns(3)
    c1.metric("Curated", len(curated_transactions))
    c2.metric("Quarantined", len(quarantine_transactions))
    total_t = len(curated_transactions) + len(quarantine_transactions)
    c3.metric("Pass Rate", f"{round(len(curated_transactions)/total_t*100, 1) if total_t > 0 else 0}%")

st.divider()

# ─── Charts ────────────────────────────────────────────────────
st.subheader("📉 Visual Breakdown")

col_left, col_right = st.columns(2)

with col_left:
    pie_data = pd.DataFrame({
        "Status": ["Curated", "Quarantined"],
        "Count": [total_curated, total_quarantine]
    })
    fig_pie = px.pie(
        pie_data,
        names="Status",
        values="Count",
        color="Status",
        color_discrete_map={"Curated": "#00cc96", "Quarantined": "#ef553b"},
        title="Overall Row Distribution"
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_right:
    if not violations.empty and "column" in violations.columns:
        violation_counts = violations.groupby(
            ["column", "rule_type"]
        ).size().reset_index(name="count")
        fig_bar = px.bar(
            violation_counts,
            x="column",
            y="count",
            color="rule_type",
            title="Violations by Column & Rule Type",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ─── AI Run Summary ────────────────────────────────────────────
st.subheader("🤖 AI Pipeline Summary")
if not summaries.empty:
    latest = summaries.iloc[-1]
    st.info(latest["summary"])
    st.caption(f"Generated at {latest['timestamp']}")
else:
    st.info("No summary available yet")

st.divider()

# ─── Root Cause Analysis ───────────────────────────────────────
st.subheader("🔬 AI Root Cause Analysis")
if not rca.empty:
    latest_rca = rca.iloc[-1]
    health = latest_rca["overall_health"]
    health_color = {
        "excellent": "🟢", "good": "🟡",
        "fair": "🟠", "poor": "🔴"
    }.get(health, "⚪")

    st.markdown(f"### Health: {health_color} {health.upper()}")
    st.info(latest_rca["executive_summary"])

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**🎯 Root Causes:**")
        root_causes = json.loads(latest_rca["root_causes"])
        for rc in root_causes:
            severity_icon = {
                "high": "🔴", "medium": "🟡", "low": "🟢"
            }.get(rc["severity"], "⚪")
            with st.expander(f"{severity_icon} {rc['cause'][:60]}..."):
                st.write(f"**Affected tables:** {rc['affected_tables']}")
                st.write(f"**Affected columns:** {rc['affected_columns']}")
                st.write(f"**Violations:** {rc['violation_count']}")

    with col2:
        st.markdown("**⚡ Priority Fixes:**")
        priority_fixes = json.loads(latest_rca["priority_fixes"])
        for fix in priority_fixes:
            effort_icon = {
                "low": "🟢", "medium": "🟡", "high": "🔴"
            }.get(fix["effort"], "⚪")
            with st.expander(
                f"{effort_icon} Resolves {fix['resolves_violations']} violations"
            ):
                st.write(fix["fix"])

    st.markdown("**🔗 Cross-table Impacts:**")
    impacts = json.loads(latest_rca["cross_table_impacts"])
    for impact in impacts:
        st.markdown(
            f"- `{impact['source_table']}` → "
            f"`{impact['downstream_table']}`: "
            f"{impact['downstream_impact']}"
        )

    st.markdown("**💡 Systemic Recommendations:**")
    recs = json.loads(latest_rca["systemic_recommendations"])
    for rec in recs:
        st.markdown(f"- {rec}")
else:
    st.info("No root cause analysis available yet")

st.divider()

# ─── Schema Drift ──────────────────────────────────────────────
st.subheader("🔄 Schema Drift Detection")
if not drift.empty:
    for _, row in drift.iterrows():
        if row["status"] == "drift_detected":
            st.warning(f"⚠️ Drift in `{row['source_name']}`")
            st.write(row["ai_explanation"])
        elif row["status"] == "no_drift":
            st.success(f"✅ No drift in `{row['source_name']}`")
        else:
            st.info(f"ℹ️ First run for `{row['source_name']}`")
else:
    st.info("No drift reports available yet")

st.divider()

# ─── Data Lineage ──────────────────────────────────────────────
st.subheader("🗺️ Data Lineage")
if not lineage.empty:
    st.dataframe(
        lineage[[
            "run_id", "source_name", "source_file",
            "total_records", "passed_records", "failed_records",
            "pass_rate", "outcome", "depends_on"
        ]],
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No lineage data available yet")

st.divider()

# ─── Curated Data ──────────────────────────────────────────────
st.subheader("✅ Curated Data")

tab1, tab2 = st.tabs(["👥 Customers", "💳 Transactions"])
with tab1:
    st.dataframe(curated_customers, use_container_width=True, hide_index=True)
with tab2:
    st.dataframe(curated_transactions, use_container_width=True, hide_index=True)

st.divider()

# ─── Quarantined Data ──────────────────────────────────────────
st.subheader("🚫 Quarantined Data")

tab1, tab2 = st.tabs(["👥 Customers", "💳 Transactions"])
with tab1:
    st.dataframe(quarantine_customers, use_container_width=True, hide_index=True)
with tab2:
    st.dataframe(quarantine_transactions, use_container_width=True, hide_index=True)

st.divider()

# ─── Violations ────────────────────────────────────────────────
st.subheader("⚠️ Violation Details")
if not violations.empty:
    col_filter, _ = st.columns([1, 3])
    with col_filter:
        selected_col = st.selectbox(
            "Filter by column",
            ["All"] + sorted(violations["column"].unique().tolist())
        )
    filtered = violations if selected_col == "All" else \
        violations[violations["column"] == selected_col]
    st.dataframe(filtered, use_container_width=True, hide_index=True)

st.divider()

# ─── AI Fix Suggestions ────────────────────────────────────────
st.subheader("🤖 AI Fix Suggestions")
if not fixes.empty:
    for _, row in fixes.iterrows():
        confidence_color = {
            "high": "🟢", "medium": "🟡", "low": "🔴"
        }.get(str(row.get("confidence", "")).lower(), "⚪")
        with st.expander(
            f"{confidence_color} Row {row['row_index']} · "
            f"Column: `{row['column']}` · "
            f"Confidence: {row.get('confidence', 'N/A')}"
        ):
            st.markdown(f"**Issue:** {row['issue']}")
            st.markdown(f"**Suggested Fix:** {row['suggested_fix']}")
else:
    st.info("No fix suggestions available")

st.divider()

# ─── Conversational Assistant ──────────────────────────────────
st.subheader("💬 Ask the Data Assistant")
st.caption("Ask anything about this pipeline run")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "data_context" not in st.session_state:
    rca_summary = rca.iloc[-1]["executive_summary"] if not rca.empty else "Not available"
    ai_summary = summaries.iloc[-1]["summary"] if not summaries.empty else "Not available"

    st.session_state.data_context = f"""
You are a data quality assistant. Answer questions about the pipeline run.
Be concise, friendly, and non-technical. Always count carefully before stating numbers.

PIPELINE DATA:
- Customers: {len(curated_customers)} curated, {len(quarantine_customers)} quarantined
- Transactions: {len(curated_transactions)} curated, {len(quarantine_transactions)} quarantined
- Total violations: {len(violations)}
- Overall pass rate: {pass_rate}%

CURATED CUSTOMERS:
{curated_customers.to_string() if not curated_customers.empty else "None"}

QUARANTINED CUSTOMERS:
{quarantine_customers.to_string() if not quarantine_customers.empty else "None"}

CURATED TRANSACTIONS:
{curated_transactions.to_string() if not curated_transactions.empty else "None"}

QUARANTINED TRANSACTIONS:
{quarantine_transactions.to_string() if not quarantine_transactions.empty else "None"}

VIOLATIONS:
{violations.to_string() if not violations.empty else "None"}

AI SUMMARY:
{ai_summary}

ROOT CAUSE ANALYSIS:
{rca_summary}
"""

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if prompt := st.chat_input("Ask about the pipeline data..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    import requests
    groq_messages = [
        {"role": "system", "content": st.session_state.data_context}
    ]
    for msg in st.session_state.messages:
        groq_messages.append({"role": msg["role"], "content": msg["content"]})

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY')}",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 500,
            "messages": groq_messages,
        }
    )

    reply = response.json()["choices"][0]["message"]["content"]
    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.write(reply)

if st.session_state.messages:
    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.rerun()

st.divider()
st.caption("Auto-refreshes every 5 minutes · Built with Streamlit + Plotly")