import streamlit as st
import pandas as pd
import sqlalchemy
import os
import plotly.express as px

DB_URL = os.environ.get("DB_URL_VAR", "postgresql://neondb_owner:npg_8om4FHVGqSLa@ep-rough-rain-ah400r1w.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require")


@st.cache_resource
def get_engine():
    return sqlalchemy.create_engine(DB_URL)


@st.cache_data(ttl=300)  # refresh every 5 minutes
def load_table(table_name):
    engine = get_engine()
    return pd.read_sql(f"SELECT * FROM {table_name}", engine)


# ─── Page Config ───────────────────────────────────────────────
st.set_page_config(
    page_title="AI Data Quality Dashboard",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 AI Data Quality Pipeline")
st.caption("Powered by Groq LLM · Airflow · Neon PostgreSQL")

# ─── Load Data ─────────────────────────────────────────────────
curated = pd.DataFrame()
quarantine = pd.DataFrame()
violations = pd.DataFrame()
fixes = pd.DataFrame()
summaries = pd.DataFrame()

try:
    curated = load_table("curated_customers")
    quarantine = load_table("quarantine_customers")
    violations = load_table("dq_violations")
    fixes = load_table("dq_fix_suggestions")
    summaries = load_table("dq_run_summaries")
except Exception as e:
    st.error(f"Database connection error: {e}")
    st.stop()

# ─── Top Metrics ───────────────────────────────────────────────
st.subheader("📊 Pipeline Summary")
col1, col2, col3, col4 = st.columns(4)

total = len(curated) + len(quarantine)
pass_rate = round(len(curated) / total * 100, 1) if total > 0 else 0

col1.metric("✅ Curated Rows", len(curated))
col2.metric("🚫 Quarantined Rows", len(quarantine))
col3.metric("⚠️ Violations Found", len(violations))
col4.metric("📈 Pass Rate", f"{pass_rate}%")

st.divider()

# ─── Pass vs Fail Chart ────────────────────────────────────────
st.subheader("📉 Pass vs Fail Breakdown")

col_left, col_right = st.columns(2)

with col_left:
    pie_data = pd.DataFrame({
        "Status": ["Curated", "Quarantined"],
        "Count": [len(curated), len(quarantine)]
    })
    fig_pie = px.pie(
        pie_data,
        names="Status",
        values="Count",
        color="Status",
        color_discrete_map={"Curated": "#00cc96", "Quarantined": "#ef553b"},
        title="Row Distribution"
    )
    st.plotly_chart(fig_pie, width="stretch")

with col_right:
    if not violations.empty:
        violation_counts = violations.groupby(
            ["column", "rule_type"]
        ).size().reset_index(name="count")
        fig_bar = px.bar(
            violation_counts,
            x="column",
            y="count",
            color="rule_type",
            title="Violations by Column & Rule Type",
            labels={"column": "Column", "count": "Violations"}
        )
        st.plotly_chart(fig_bar, width="stretch")

st.divider()

# ─── Curated Data ──────────────────────────────────────────────
st.subheader("✅ Curated Data")
st.dataframe(
    curated,
    width="stretch",
    hide_index=True
)

st.divider()

# ─── Quarantined Data ──────────────────────────────────────────
st.subheader("🚫 Quarantined Data")
st.dataframe(
    quarantine,
    width="stretch",
    hide_index=True
)

st.divider()

# ─── Violations Table ──────────────────────────────────────────
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
    st.dataframe(filtered, width="stretch", hide_index=True)

st.divider()

# ─── AI Fix Suggestions ────────────────────────────────────────
st.subheader("🤖 AI Fix Suggestions")
if not fixes.empty:
    for _, row in fixes.iterrows():
        confidence_color = {
            "high": "🟢",
            "medium": "🟡",
            "low": "🔴"
        }.get(str(row.get("confidence", "")).lower(), "⚪")

        with st.expander(
            f"{confidence_color} Row {row['row_index']} · "
            f"Column: `{row['column']}` · "
            f"Confidence: {row.get('confidence', 'N/A')}"
        ):
            st.markdown(f"**Issue:** {row['issue']}")
            st.markdown(f"**Suggested Fix:** {row['suggested_fix']}")
else:
    st.info("No fix suggestions available.")

st.divider()
st.caption("Auto-refreshes every 5 minutes · Built with Streamlit + Plotly")

# ─── AI Run Summary ────────────────────────────────────────────
st.subheader("🤖 AI Pipeline Summary")
try:
    summaries = load_table("dq_run_summaries")
    if not summaries.empty:
        latest = summaries.iloc[-1]
        st.info(latest["summary"])
        st.caption(f"Generated at {latest['timestamp']}")
except Exception:
    st.warning("No summary available yet — run the pipeline first.")

# ─── Schema Drift ──────────────────────────────────────────────
st.subheader("🔄 Schema Drift Detection")
try:
    drift = load_table("dq_drift_reports")
    if not drift.empty:
        latest = drift.iloc[-1]
        if latest["status"] == "drift_detected":
            st.warning(f"⚠️ Schema drift detected in last run!")
            st.write(latest["ai_explanation"])
            with st.expander("View raw changes"):
                st.json(latest["changes"])
        elif latest["status"] == "no_drift":
            st.success("✅ No schema drift detected in last run")
        else:
            st.info("ℹ️ First pipeline run — schema baseline established")
except Exception:
    st.info("No drift reports available yet")

# ─── Conversational Assistant ──────────────────────────────────
st.divider()
st.subheader("💬 Ask the Data Assistant")
st.caption("Ask anything about this pipeline run")

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "data_context" not in st.session_state:
    st.session_state.data_context = f"""
You are a data quality assistant. Answer questions about the pipeline run below.
Be concise, friendly, and non-technical. Always count carefully before 
stating numbers. Double-check your figures before responding.
Be concise, friendly, and non-technical. Use plain English.

PIPELINE DATA:
- Total records processed: {len(curated) + len(quarantine)}
- Curated (passed): {len(curated)} rows
- Quarantined (failed): {len(quarantine)} rows
- Pass rate: {pass_rate}%
- Violations found: {len(violations)}

CURATED RECORDS:
{curated.to_string() if not curated.empty else "None"}

QUARANTINED RECORDS:
{quarantine.to_string() if not quarantine.empty else "None"}

VIOLATIONS:
{violations.to_string() if not violations.empty else "None"}

FIX SUGGESTIONS:
{fixes.to_string() if not fixes.empty else "None"}

LATEST AI SUMMARY:
{summaries.iloc[-1]["summary"] if not summaries.empty else "Not available"}
"""

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Chat input
if prompt := st.chat_input("Ask about the pipeline data..."):
    # Add user message to history
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.write(prompt)

    # Build messages for Groq
    groq_messages = [
        {
            "role": "system",
            "content": st.session_state.data_context
        }
    ]

    # Add conversation history
    for msg in st.session_state.messages:
        groq_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    # Call Groq
    import requests
    import os

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

    # Add assistant reply to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": reply
    })

    with st.chat_message("assistant"):
        st.write(reply)

# Clear chat button
if st.session_state.messages:
    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.rerun()