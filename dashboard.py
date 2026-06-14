import streamlit as st
import pandas as pd
import sqlalchemy
import os
import plotly.express as px

DB_URL = os.environ.get("DB_URL_VAR", "")


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
try:
    curated = load_table("curated_customers")
    quarantine = load_table("quarantine_customers")
    violations = load_table("dq_violations")
    fixes = load_table("dq_fix_suggestions")
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
    st.plotly_chart(fig_pie, use_container_width=True)

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
        st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ─── Curated Data ──────────────────────────────────────────────
st.subheader("✅ Curated Data")
st.dataframe(
    curated,
    use_container_width=True,
    hide_index=True
)

st.divider()

# ─── Quarantined Data ──────────────────────────────────────────
st.subheader("🚫 Quarantined Data")
st.dataframe(
    quarantine,
    use_container_width=True,
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
    st.dataframe(filtered, use_container_width=True, hide_index=True)

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