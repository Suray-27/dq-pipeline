import streamlit as st
import pandas as pd
import os
import json
import requests
import plotly.express as px
from dotenv import load_dotenv
from snowflake.sqlalchemy import URL
from sqlalchemy import create_engine, text
load_dotenv()

# ─── Page Config ───────────────────────────────────────────────
st.set_page_config(
    page_title="DQ Pipeline",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Theme Toggle ──────────────────────────────────────────────
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

dark = st.session_state.dark_mode

# ─── Theme Variables ───────────────────────────────────────────
if dark:
    bg         = "#0f1117"
    sidebar_bg = "#161b27"
    card_bg    = "#161b27"
    border     = "#1e2535"
    text_color = "#e2e8f0"
    subtext    = "#7c8db5"
    accent     = "#60a5fa"
    green      = "#4ade80"
    red        = "#f87171"
    orange     = "#fb923c"
    chart_bg   = "rgba(0,0,0,0)"
    grid_color = "#1e2535"
else:
    bg         = "#f8fafc"
    sidebar_bg = "#f1f5f9"
    card_bg    = "#ffffff"
    border     = "#e2e8f0"
    text_color = "#0f172a"
    subtext    = "#64748b"
    accent     = "#2563eb"
    green      = "#16a34a"
    red        = "#dc2626"
    orange     = "#ea580c"
    chart_bg   = "rgba(0,0,0,0)"
    grid_color = "#e2e8f0"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background-color: {bg}; color: {text}; }}
    [data-testid="stSidebar"] {{ background-color: {sidebar_bg}; border-right: 1px solid {border}; }}
    [data-testid="metric-container"] {{
        background: {card_bg};
        border: 1px solid {border};
        border-radius: 12px;
        padding: 16px;
    }}
    [data-testid="metric-container"] label {{
        color: {subtext} !important;
        font-size: 12px !important;
        font-weight: 500 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    [data-testid="metric-container"] [data-testid="stMetricValue"] {{
        color: {text_color} !important;
        font-size: 28px !important;
        font-weight: 700 !important;
    }}
    .section-header {{
        font-size: 13px;
        font-weight: 600;
        color: {subtext};
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid {border};
    }}
    .health-badge {{
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.05em;
    }}
    .health-poor     {{ background: #fef2f2; color: #dc2626; border: 1px solid #dc2626; }}
    .health-fair     {{ background: #fff7ed; color: #ea580c; border: 1px solid #ea580c; }}
    .health-good     {{ background: #f0fdf4; color: #16a34a; border: 1px solid #16a34a; }}
    .health-excellent {{ background: #ecfdf5; color: #059669; border: 1px solid #059669; }}
    .run-chip {{
        display: inline-block;
        background: {card_bg};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 3px 10px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
        color: {subtext};
    }}
    [data-testid="stDataFrame"] {{ border: 1px solid {border} !important; border-radius: 8px !important; }}
    [data-testid="stExpander"] {{ background: {card_bg}; border: 1px solid {border}; border-radius: 8px; }}
    [data-testid="stChatMessage"] {{ background: {card_bg}; border: 1px solid {border}; border-radius: 10px; }}
    hr {{ border-color: {border} !important; margin: 24px 0 !important; }}
    p, label, span, div {{ color: {text_color}; }}
</style>
""", unsafe_allow_html=True)


# ─── Connection ────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    return create_engine(URL(
        account=os.environ.get("SNOWFLAKE_ACCOUNT"),
        user=os.environ.get("SNOWFLAKE_USER"),
        password=os.environ.get("SNOWFLAKE_PASSWORD"),
        database=os.environ.get("SNOWFLAKE_DATABASE"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
    ))


def query(sql: str) -> pd.DataFrame:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            return pd.DataFrame(result.fetchall(), columns=list(result.keys()))
    except Exception as e:
        st.sidebar.error(f"Database Error: {e}")  # Avoid swallowing the error silently
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def load_dashboard_data():
    """Load only aggregated stats — no full table scans."""
    return {
        # Counts only
        "count_curated_customers": query("SELECT COUNT(*) FROM CURATED_CUSTOMERS").iloc[0].iat[0] if not query("SELECT COUNT(*) FROM CURATED_CUSTOMERS").empty else 0,
        "count_quarantine_customers": query("SELECT COUNT(*) as n FROM QUARANTINE_CUSTOMERS").iloc[0].iat[0] if not query("SELECT COUNT(*) as n FROM QUARANTINE_CUSTOMERS").empty else 0,
        "count_curated_transactions": query("SELECT COUNT(*) as n FROM CURATED_TRANSACTIONS").iloc[0].iat[0] if not query("SELECT COUNT(*) as n FROM CURATED_TRANSACTIONS").empty else 0,
        "count_quarantine_transactions": query("SELECT COUNT(*) as n FROM QUARANTINE_TRANSACTIONS").iloc[0].iat[0] if not query("SELECT COUNT(*) as n FROM QUARANTINE_TRANSACTIONS").empty else 0,

        # Violations grouped — not raw rows
        "violations_grouped": query("""
            SELECT COLUMN_NAME, RULE_TYPE, COUNT(*) as count
            FROM DQ_VIOLATIONS
            WHERE DATE(CAPTURED_AT) = CURRENT_DATE()
            GROUP BY COLUMN_NAME, RULE_TYPE
            ORDER BY count DESC
        """),

        # Latest summary only
        "summary": query("""
            SELECT SUMMARY, TIMESTAMP
            FROM DQ_RUN_SUMMARIES
            ORDER BY TIMESTAMP DESC
            LIMIT 1
        """),

        # Latest RCA only
        "rca": query("""
            SELECT *
            FROM DQ_ROOT_CAUSE_ANALYSIS
            ORDER BY CAPTURED_AT DESC
            LIMIT 1
        """),

        # Latest drift per source — not history
        # Latest drift per source
        "drift": query("""
            SELECT SOURCE_NAME, STATUS, AI_EXPLANATION, RUN_ID
            FROM DQ_DRIFT_REPORTS
            QUALIFY ROW_NUMBER() OVER (PARTITION BY SOURCE_NAME ORDER BY RUN_ID DESC) = 1
        """),

        # Latest 10 lineage records
        "lineage": query("""
            SELECT RUN_ID, SOURCE_NAME, SOURCE_FILE,
                   TOTAL_RECORDS, PASSED_RECORDS, FAILED_RECORDS,
                   PASS_RATE, OUTCOME, DEPENDS_ON, CAPTURED_AT
            FROM DATA_LINEAGE
            ORDER BY CAPTURED_AT DESC
            LIMIT 10
        """),

        # Today's fixes only
        "fixes": query("""
            SELECT *
            FROM DQ_FIX_SUGGESTIONS
            WHERE DATE(CAPTURED_AT) = CURRENT_DATE()
            ORDER BY ROW_INDEX
        """),

        # Violation count for sidebar
        "violation_count": query("""
            SELECT COUNT(*) as n FROM DQ_VIOLATIONS
            WHERE DATE(CAPTURED_AT) = CURRENT_DATE()
        """),
    }


# ─── Load Data ─────────────────────────────────────────────────
with st.spinner("Loading pipeline data..."):
    data = load_dashboard_data()

cc  = data["count_curated_customers"]
qc  = data["count_quarantine_customers"]
ct  = data["count_curated_transactions"]
qt  = data["count_quarantine_transactions"]
vg  = data["violations_grouped"]
summ = data["summary"]
rca  = data["rca"]
drift = data["drift"]
lineage = data["lineage"]
fixes = data["fixes"]
vc_row = data["violation_count"]

total_curated    = cc + ct
total_quarantine = qc + qt
total            = total_curated + total_quarantine
pass_rate        = round(total_curated / total * 100, 1) if total > 0 else 0
violation_count  = int(vc_row.iloc[0].iat[0]) if not vc_row.empty else 0
if not rca.empty:
    # 1. Force column headers to uppercase to beat casing issues
    rca.columns = [c.upper() for c in rca.columns]
    
    # 2. Safely grab the index location of the column
    col_idx = list(rca.columns).index("OVERALL_HEALTH")
    
    # 3. Use .iat[row, column] for lightning-fast, safe value extraction
    health = str(rca.iat[0, col_idx]).lower()
else:
    health = "unknown"


# ─── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### 🔍 DQ Pipeline")
    st.markdown("---")

    # Theme toggle
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"<p style='color:{subtext};font-size:13px;margin:0'>{'🌙 Dark Mode' if dark else '☀️ Light Mode'}</p>", unsafe_allow_html=True)
    with col2:
        if st.button("⇄", key="theme_toggle"):
            st.session_state.dark_mode = not st.session_state.dark_mode
            st.rerun()

    st.markdown("---")

    page = st.radio(
        "Navigate",
        ["📊 Overview", "⚠️ Violations", "🔬 Root Cause",
         "🔄 Drift & Lineage", "💬 Ask AI"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    st.markdown(f'<p class="section-header">Pipeline Status</p>', unsafe_allow_html=True)

    health_class = f"health-{health}"
    st.markdown(
        f'<span class="health-badge {health_class}">{health.upper()}</span>',
        unsafe_allow_html=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    if not lineage.empty and "RUN_ID" in lineage.columns:
        latest_run = lineage.iloc[0]["RUN_ID"]
        st.markdown(
            f'<p style="font-size:11px;color:{subtext};">Latest Run</p>'
            f'<span class="run-chip">{latest_run}</span>',
            unsafe_allow_html=True
        )

    st.markdown("---")
    st.markdown(
        f'<p style="font-size:11px;color:{subtext};">Powered by Groq · Snowflake<br>Refreshes every 5 min</p>',
        unsafe_allow_html=True
    )

    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

chart_theme_layout = dict(
    paper_bgcolor=chart_bg,
    plot_bgcolor=chart_bg,
    font_color=text_color,  # Double check you renamed this from 'text' earlier!
    xaxis=dict(gridcolor=grid_color, color=subtext),
    yaxis=dict(gridcolor=grid_color, color=subtext),
    margin=dict(t=40, b=0, l=0, r=0)
)

# ════════════════════════════════════════════════════════════════
# PAGE: OVERVIEW
# ════════════════════════════════════════════════════════════════
if page == "📊 Overview":

    st.markdown(f"## Pipeline Overview")
    st.markdown(f"<p style='color:{subtext}'>Real-time data quality metrics across all sources.</p>", unsafe_allow_html=True)
    st.markdown("---")

    # Top metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ Curated", total_curated)
    col2.metric("🚫 Quarantined", total_quarantine)
    col3.metric("⚠️ Violations Today", violation_count)
    col4.metric("📈 Pass Rate", f"{pass_rate}%")

    st.markdown("---")
    st.markdown(f'<p class="section-header">Per Table Breakdown</p>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    total_c = cc + qc
    rate_c  = round(cc / total_c * 100, 1) if total_c > 0 else 0
    total_t = ct + qt
    rate_t  = round(ct / total_t * 100, 1) if total_t > 0 else 0

    with col1:
        st.markdown(f"""
        <div style="background:{card_bg};border:1px solid {border};border-radius:12px;padding:20px;">
            <p style="color:{subtext};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 12px 0;">👥 Customers</p>
            <div style="display:flex;gap:24px;">
                <div><p style="color:{green};font-size:24px;font-weight:700;margin:0">{cc}</p><p style="color:{subtext};font-size:12px;margin:0">Curated</p></div>
                <div><p style="color:{red};font-size:24px;font-weight:700;margin:0">{qc}</p><p style="color:{subtext};font-size:12px;margin:0">Quarantined</p></div>
                <div><p style="color:{accent};font-size:24px;font-weight:700;margin:0">{rate_c}%</p><p style="color:{subtext};font-size:12px;margin:0">Pass Rate</p></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div style="background:{card_bg};border:1px solid {border};border-radius:12px;padding:20px;">
            <p style="color:{subtext};font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin:0 0 12px 0;">💳 Transactions</p>
            <div style="display:flex;gap:24px;">
                <div><p style="color:{green};font-size:24px;font-weight:700;margin:0">{ct}</p><p style="color:{subtext};font-size:12px;margin:0">Curated</p></div>
                <div><p style="color:{red};font-size:24px;font-weight:700;margin:0">{qt}</p><p style="color:{subtext};font-size:12px;margin:0">Quarantined</p></div>
                <div><p style="color:{accent};font-size:24px;font-weight:700;margin:0">{rate_t}%</p><p style="color:{subtext};font-size:12px;margin:0">Pass Rate</p></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col_left, col_right = st.columns(2)

    with col_left:
        fig_pie = px.pie(
            pd.DataFrame({"Status": ["Curated", "Quarantined"], "Count": [total_curated, total_quarantine]}),
            names="Status", values="Count", color="Status",
            color_discrete_map={"Curated": green, "Quarantined": red},
            hole=0.5,
        )
        fig_pie.update_layout(
            paper_bgcolor=chart_bg, plot_bgcolor=chart_bg,
            font_color=text_color,
            legend=dict(font=dict(color=subtext)),
            title=dict(text="Pass vs Quarantine", font=dict(color=text_color, size=14)),
            margin=dict(t=40, b=0, l=0, r=0),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_right:
        if not vg.empty:
            col_key = "COLUMN_NAME" if "COLUMN_NAME" in vg.columns else "column_name"
            rule_key = "RULE_TYPE" if "RULE_TYPE" in vg.columns else "rule_type"
            count_key = "COUNT" if "COUNT" in vg.columns else "count"
            fig_bar = px.bar(
                vg, x=col_key, y=count_key, color=rule_key,
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig_bar.update_layout(
                paper_bgcolor=chart_bg, plot_bgcolor=chart_bg,
                font_color=text_color,
                xaxis=dict(gridcolor=grid_color, color=subtext),
                yaxis=dict(gridcolor=grid_color, color=subtext),
                legend=dict(font=dict(color=subtext)),
                title=dict(text="Violations by Column (Today)", font=dict(color=text_color, size=14)),
                margin=dict(t=40, b=0, l=0, r=0),
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No violations today ✅")

    st.markdown("---")
    st.markdown(f'<p class="section-header">AI Run Summary</p>', unsafe_allow_html=True)
    if not summ.empty:
        summary_col = "SUMMARY" if "SUMMARY" in summ.columns else "summary"
        ts_col = "TIMESTAMP" if "TIMESTAMP" in summ.columns else "timestamp"
        st.markdown(f"""
        <div style="background:{card_bg};border:1px solid {border};border-left:3px solid {accent};border-radius:8px;padding:16px 20px;">
            <p style="color:{text_color};line-height:1.7;margin:0">{summ.iloc[0][summary_col]}</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f'<p style="color:{subtext};font-size:12px;margin-top:8px;">Generated at {summ.iloc[0][ts_col]}</p>', unsafe_allow_html=True)
    else:
        st.info("No summary available yet — run the pipeline first")


# ════════════════════════════════════════════════════════════════
# PAGE: VIOLATIONS
# ════════════════════════════════════════════════════════════════
elif page == "⚠️ Violations":
    st.markdown("## Violations & Fixes")
    st.markdown(f"<p style='color:{subtext}'>Today's data quality rule failures with AI-suggested fixes.</p>", unsafe_allow_html=True)
    st.markdown("---")

    if not vg.empty:
        col_key   = "COLUMN_NAME" if "COLUMN_NAME" in vg.columns else "column_name"
        rule_key  = "RULE_TYPE" if "RULE_TYPE" in vg.columns else "rule_type"
        count_key = "COUNT" if "COUNT" in vg.columns else "count"

        st.markdown(f'<p class="section-header">Violation Summary — Today</p>', unsafe_allow_html=True)
        st.dataframe(vg, use_container_width=True, hide_index=True)

        # Totals per column
        total_by_col = vg.groupby(col_key)[count_key].sum().reset_index()
        fig = px.bar(
            total_by_col, x=col_key, y=count_key,
            color_discrete_sequence=[accent],
            title="Total Violations per Column"
        )
        
        # Safe structural dictionary update
        fig.update_layout(chart_theme_layout)
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.success("✅ No violations today — all records passed quality checks!")

    st.markdown("---")
    st.markdown(f'<p class="section-header">AI Fix Suggestions — Today</p>', unsafe_allow_html=True)

    if not fixes.empty:
        col_key = "column_name" if "column_name" in fixes.columns else \
                  "COLUMN_NAME" if "COLUMN_NAME" in fixes.columns else "column"

        for _, row in fixes.iterrows():
            confidence = str(row.get("confidence", row.get("CONFIDENCE", ""))).lower()
            conf_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")
            col_val = row.get(col_key, "unknown")

            with st.expander(f"{conf_icon} Row {row.get('row_index', row.get('ROW_INDEX', '?'))} · `{col_val}` · {confidence.upper()} confidence"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Issue**")
                    st.markdown(f"<p style='color:{red}'>{row.get('issue', row.get('ISSUE', ''))}</p>", unsafe_allow_html=True)
                with c2:
                    st.markdown("**Suggested Fix**")
                    st.markdown(f"<p style='color:{green}'>{row.get('suggested_fix', row.get('SUGGESTED_FIX', ''))}</p>", unsafe_allow_html=True)
    else:
        st.info("No fix suggestions for today's run")


# ════════════════════════════════════════════════════════════════
# PAGE: ROOT CAUSE
# ════════════════════════════════════════════════════════════════
elif page == "🔬 Root Cause":
    st.markdown("## AI Root Cause Analysis")
    st.markdown(f"<p style='color:{subtext}'>Latest cross-table pattern analysis powered by Qwen3-32b.</p>", unsafe_allow_html=True)
    st.markdown("---")

    if not rca.empty:
        latest = rca.iloc[0]
        health = latest.get("OVERALL_HEALTH", latest.get("overall_health", "unknown"))
        exec_summary = latest.get("EXECUTIVE_SUMMARY", latest.get("executive_summary", ""))

        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(f'<span class="health-badge health-{health}">{health.upper()}</span>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<p style="color:{text_color};line-height:1.6">{exec_summary}</p>', unsafe_allow_html=True)

        st.markdown("---")
        col1, col2 = st.columns(2)

        def get_json(row, key):
            val = row.get(key.upper(), row.get(key.lower(), "[]"))
            try:
                return json.loads(val) if isinstance(val, str) else val
            except:
                return []

        with col1:
            st.markdown(f'<p class="section-header">Root Causes</p>', unsafe_allow_html=True)
            for rc in get_json(latest, "root_causes"):
                sev = rc.get("severity", "medium")
                sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
                with st.expander(f"{sev_icon} {rc.get('cause', '')[:70]}"):
                    st.markdown(f"**Affected tables:** {', '.join(rc.get('affected_tables', []))}")
                    st.markdown(f"**Affected columns:** {', '.join(rc.get('affected_columns', []))}")
                    st.markdown(f"**Violations:** {rc.get('violation_count', 0)}")

        with col2:
            st.markdown(f'<p class="section-header">Priority Fixes</p>', unsafe_allow_html=True)
            for fix in get_json(latest, "priority_fixes"):
                effort = fix.get("effort", "medium")
                effort_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(effort, "⚪")
                with st.expander(f"{effort_icon} Resolves {fix.get('resolves_violations', 0)} violations · {effort.upper()} effort"):
                    st.markdown(fix.get("fix", ""))

        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f'<p class="section-header">Cross-table Impacts</p>', unsafe_allow_html=True)
            for impact in get_json(latest, "cross_table_impacts"):
                st.markdown(f"""
                <div style="background:{card_bg};border:1px solid {border};border-radius:8px;padding:12px;margin-bottom:8px;">
                    <p style="margin:0;color:{text_color}">
                        <code style="color:{accent}">{impact.get('source_table','')}</code>
                        <span style="color:{subtext}"> → </span>
                        <code style="color:{accent}">{impact.get('downstream_table','')}</code>
                    </p>
                    <p style="margin:4px 0 0 0;color:{subtext};font-size:13px">{impact.get('downstream_impact','')}</p>
                </div>
                """, unsafe_allow_html=True)

        with col2:
            st.markdown(f'<p class="section-header">Systemic Recommendations</p>', unsafe_allow_html=True)
            for i, rec in enumerate(get_json(latest, "systemic_recommendations"), 1):
                st.markdown(f"""
                <div style="background:{card_bg};border:1px solid {border};border-radius:8px;padding:12px;margin-bottom:8px;">
                    <p style="margin:0;color:{text_color};font-size:13px">
                        <span style="color:{accent};font-weight:600">{i}.</span> {rec}
                    </p>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No root cause analysis available yet — run the pipeline first")


# ════════════════════════════════════════════════════════════════
# PAGE: DRIFT & LINEAGE
# ════════════════════════════════════════════════════════════════
elif page == "🔄 Drift & Lineage":
    st.markdown("## Schema Drift & Data Lineage")
    st.markdown(f"<p style='color:{subtext}'>Latest schema state per source and recent pipeline runs.</p>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown(f'<p class="section-header">Schema Drift — Current State</p>', unsafe_allow_html=True)
    st.caption("Shows the most recent drift check per source table only")

    if not drift.empty:
        status_col = "STATUS" if "STATUS" in drift.columns else "status"
        source_col = "SOURCE_NAME" if "SOURCE_NAME" in drift.columns else "source_name"
        expl_col   = "AI_EXPLANATION" if "AI_EXPLANATION" in drift.columns else "ai_explanation"

        for _, row in drift.iterrows():
            status  = row[status_col]
            source  = row[source_col]
            expl    = row[expl_col]

            if status == "drift_detected":
                st.markdown(f"""
                <div style="background:#fef2f2;border:1px solid {red};border-radius:8px;padding:16px;margin-bottom:8px;">
                    <p style="color:{red};font-weight:600;margin:0 0 8px 0">⚠️ Schema drift in <code>{source}</code></p>
                    <p style="color:#7f1d1d;font-size:13px;margin:0">{expl}</p>
                </div>
                """, unsafe_allow_html=True)
            elif status == "no_drift":
                st.markdown(f"""
                <div style="background:#f0fdf4;border:1px solid {green};border-radius:8px;padding:12px;margin-bottom:8px;">
                    <p style="color:{green};margin:0;font-size:13px">✅ No schema drift in <code>{source}</code></p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background:#eff6ff;border:1px solid {accent};border-radius:8px;padding:12px;margin-bottom:8px;">
                    <p style="color:{accent};margin:0;font-size:13px">ℹ️ First run baseline set for <code>{source}</code></p>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No drift reports available yet")

    st.markdown("---")
    st.markdown(f'<p class="section-header">Data Lineage — Last 10 Runs</p>', unsafe_allow_html=True)

    if not lineage.empty:
        # Normalize column names to uppercase
        lineage.columns = [c.upper() for c in lineage.columns]
        cols_to_show = [c for c in [
            "RUN_ID", "SOURCE_NAME", "TOTAL_RECORDS", "PASSED_RECORDS",
            "FAILED_RECORDS", "PASS_RATE", "OUTCOME", "DEPENDS_ON", "CAPTURED_AT"
        ] if c in lineage.columns]

        def color_outcome(val):
            colors = {"success": f"color: {green}", "partial": f"color: {orange}", "failed": f"color: {red}"}
            return colors.get(str(val).lower(), "")

        if cols_to_show:
            styled = lineage[cols_to_show].style.map(
                        color_outcome, subset=["OUTCOME"] if "OUTCOME" in cols_to_show else []
                        )
            st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.info("No lineage data available yet")


# ════════════════════════════════════════════════════════════════
# PAGE: ASK AI
# ════════════════════════════════════════════════════════════════
elif page == "💬 Ask AI":
    st.markdown("## Data Assistant")
    st.markdown(f"<p style='color:{subtext}'>Ask anything about today's pipeline run in plain English.</p>", unsafe_allow_html=True)
    st.markdown("---")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Build AI context — load current run data only when chat opens
    if "data_context" not in st.session_state:
        with st.spinner("Loading context for AI assistant..."):
            quarantine_c = query("SELECT * FROM QUARANTINE_CUSTOMERS WHERE DATE(CAPTURED_AT) = CURRENT_DATE()")
            quarantine_t = query("SELECT * FROM QUARANTINE_TRANSACTIONS WHERE DATE(CAPTURED_AT) = CURRENT_DATE()")
            violations_full = query("SELECT * FROM DQ_VIOLATIONS WHERE DATE(CAPTURED_AT) = CURRENT_DATE()")

        rca_summary = rca.iloc[0].get("EXECUTIVE_SUMMARY", "") if not rca.empty else "Not available"
        ai_summary  = summ.iloc[0].get("SUMMARY", "") if not summ.empty else "Not available"

        st.session_state.data_context = f"""
You are a data quality assistant. Answer questions about today's pipeline run.
Be concise, friendly, and non-technical. Count carefully before stating numbers.
Stay on topic — only answer questions about this pipeline data.

PIPELINE SUMMARY:
- Customers: {cc} curated, {qc} quarantined
- Transactions: {ct} curated, {qt} quarantined
- Total violations today: {violation_count}
- Overall pass rate: {pass_rate}%
- Pipeline health: {health}

QUARANTINED CUSTOMERS (today):
{quarantine_c.to_string() if not quarantine_c.empty else "None"}

QUARANTINED TRANSACTIONS (today):
{quarantine_t.to_string() if not quarantine_t.empty else "None"}

VIOLATIONS (today):
{violations_full.to_string() if not violations_full.empty else "None"}

AI RUN SUMMARY:
{ai_summary}

ROOT CAUSE ANALYSIS:
{rca_summary}
"""

    # Suggested questions
    if not st.session_state.messages:
        st.markdown(f'<p class="section-header">Try asking</p>', unsafe_allow_html=True)
        suggestions = [
            "Why was Eve Davis quarantined?",
            "Which column had the most violations?",
            "What's the most impactful fix?",
            "Summarize quarantined transactions",
            "How can we improve our pass rate?",
        ]
        cols = st.columns(len(suggestions))
        for i, s in enumerate(suggestions):
            with cols[i]:
                if st.button(s, use_container_width=True, key=f"suggest_{i}"):
                    st.session_state.messages.append({"role": "user", "content": s})
                    st.rerun()
        st.markdown("---")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Ask about today's pipeline data..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        groq_messages = [{"role": "system", "content": st.session_state.data_context}]
        for msg in st.session_state.messages:
            groq_messages.append({"role": msg["role"], "content": msg["content"]})

        with st.spinner("Thinking..."):
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY')}"},
                json={"model": "llama-3.3-70b-versatile", "max_tokens": 500, "messages": groq_messages}
            )
            reply = resp.json()["choices"][0]["message"]["content"]

        st.session_state.messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.write(reply)

    if st.session_state.messages:
        st.markdown("---")
        if st.button("🗑️ Clear conversation"):
            st.session_state.messages = []
            st.rerun()