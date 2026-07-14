import os
import json
import requests
import pandas as pd
from datetime import datetime
from config import get_engine, TABLES


def _call_groq(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=body,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


DRIFT_PROMPT = """You are a data engineering expert.
Compare the previous and current schema of a data table and explain
any changes in plain English for business stakeholders.

For each change explain:
- What changed
- What the business risk is
- What action should be taken

Previous schema:
{previous}

Current schema:
{current}

If no changes found, say "No schema drift detected."
Keep it concise and non-technical.
"""


def save_schema(df: pd.DataFrame, source_name: str, run_id: str):
    engine = get_engine()
    records = []
    for col, dtype in df.dtypes.items():
        records.append({
            "source_name": source_name,
            "column_name": col,
            "dtype": str(dtype),
            "pipeline_run_id": run_id,
            "captured_at": datetime.now().isoformat(),
        })
    pd.DataFrame(records).to_sql(
        TABLES["schema_reg"], engine,
        if_exists="append", index=False
    )
    print(f"[Drift] Saved schema for '{source_name}' — {len(records)} columns")


def get_previous_schema(source_name: str) -> dict:
    engine = get_engine()
    target_table = str(TABLES["schema_reg"]).lower().strip()
    try:
        query = f"""
            SELECT column_name, dtype
            FROM {target_table}
            WHERE lower(source_name) = '{str(source_name).lower().strip()}'
            AND pipeline_run_id = (
                SELECT pipeline_run_id
                FROM {target_table}
                WHERE lower(source_name) = '{str(source_name).lower().strip()}'
                ORDER BY captured_at DESC
                LIMIT 1
            )
        """
        df = pd.read_sql(query, engine)
        # Normalize column name keys to lowercase to prevent string-matching bugs
        return {str(k).lower(): str(v).lower() for k, v in zip(df["column_name"], df["dtype"])}
    except Exception as e:
        print(f"[Drift] Warning: Baseline schema check missed: {e}")
        return {}

def detect_drift(df: pd.DataFrame, source_name: str, run_id: str) -> dict:
    # 1. Fetch historical schema from Snowflake
    previous = get_previous_schema(source_name)
    current = dict(df.dtypes.astype(str))

    # 2. Save the current schema as the new baseline for the next run
    save_schema(df, source_name, run_id)

    # ─── CONDITION 1: ABSOLUTE FIRST LOAD ──────────────────────────────────
    if not previous:
        print(f"[Drift] First run for '{source_name}' — baseline established. Skipping AI call.")
        return {
            "source_name": source_name,
            "run_id": run_id,
            "status": "first_run",
            "changes": [],
            "ai_explanation": "First pipeline run — schema baseline established successfully.",
        }

    # Evaluate structural changes
    changes = []
    for col in current:
        if col not in previous:
            changes.append({"type": "new_column", "column": col, "dtype": current[col]})
    for col in previous:
        if col not in current:
            changes.append({"type": "missing_column", "column": col, "previous_dtype": previous[col]})
    for col in current:
        if col in previous and current[col] != previous[col]:
            changes.append({
                "type": "dtype_changed",
                "column": col,
                "previous_dtype": previous[col],
                "current_dtype": current[col],
            })

    # ─── CONDITION 2: SUBSEQUENT LOAD W/ CHANGES DETECTED ────────────────
    if changes:
        print(f"[Drift] Alert: {len(changes)} structural shifts found for '{source_name}' — calling Groq...")
        prompt = DRIFT_PROMPT.format(
            previous=json.dumps(previous, indent=2),
            current=json.dumps(current, indent=2),
        )
        ai_explanation = _call_groq(prompt)
        status = "drift_detected"
        
    # ─── CONDITION 3: ROUTINE RUN (DATA CHANGES, SCHEMA IDENTICAL) ────────
    else:
        print(f"[Drift] Schema matches historical baseline for '{source_name}' — skipping Groq.")
        ai_explanation = "No schema drift detected."
        status = "no_drift"

    return {
        "source_name": source_name,
        "run_id": run_id,
        "status": status,
        "changes": changes,
        "ai_explanation": ai_explanation,
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    from config import SOURCES
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    print("--- Checking Schema Drift Across All Enterprise Core Tables ---")
    
    for source_name, source_info in SOURCES.items():
        from extract import extract
        df = extract(source_info["file"])
        report = detect_drift(df, source_name=source_name, run_id=run_id)
        print(f" -> {source_name} status: {report['status']}")