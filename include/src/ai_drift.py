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
    try:
        query = f"""
            SELECT column_name, dtype
            FROM {TABLES["schema_reg"]}
            WHERE source_name = '{source_name}'
            AND pipeline_run_id = (
                SELECT pipeline_run_id
                FROM {TABLES["schema_reg"]}
                WHERE source_name = '{source_name}'
                ORDER BY captured_at DESC
                LIMIT 1
            )
        """
        df = pd.read_sql(query, engine)
        return dict(zip(df["column_name"], df["dtype"]))
    except Exception:
        return {}


def detect_drift(df: pd.DataFrame, source_name: str, run_id: str) -> dict:
    previous = get_previous_schema(source_name)
    current = dict(df.dtypes.astype(str))

    save_schema(df, source_name, run_id)

    if not previous:
        print(f"[Drift] First run for '{source_name}' — no drift check needed")
        return {
            "source_name": source_name,
            "run_id": run_id,
            "status": "first_run",
            "changes": [],
            "ai_explanation": "First pipeline run — schema baseline established.",
        }

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

    if changes:
        print(f"[Drift] {len(changes)} changes detected — calling Groq...")
        prompt = DRIFT_PROMPT.format(
            previous=json.dumps(previous, indent=2),
            current=json.dumps(current, indent=2),
        )
        ai_explanation = _call_groq(prompt)
    else:
        ai_explanation = "No schema drift detected."

    return {
        "source_name": source_name,
        "run_id": run_id,
        "status": "drift_detected" if changes else "no_drift",
        "changes": changes,
        "ai_explanation": ai_explanation,
    }

    # Detect changes
    changes = []

    # New columns
    for col in current:
        if col not in previous:
            changes.append({
                "type": "new_column",
                "column": col,
                "dtype": current[col],
            })

    # Missing columns
    for col in previous:
        if col not in current:
            changes.append({
                "type": "missing_column",
                "column": col,
                "previous_dtype": previous[col],
            })

    # Dtype changes
    for col in current:
        if col in previous and current[col] != previous[col]:
            changes.append({
                "type": "dtype_changed",
                "column": col,
                "previous_dtype": previous[col],
                "current_dtype": current[col],
            })

    # Call AI only if changes detected
    if changes:
        print(f"[Drift] {len(changes)} changes detected — calling Groq...")
        prompt = DRIFT_PROMPT.format(
            previous=json.dumps(previous, indent=2),
            current=json.dumps(current, indent=2),
        )
        ai_explanation = _call_groq(prompt)
    else:
        ai_explanation = "No schema drift detected."

    return {
        "source_name": source_name,
        "run_id": run_id,
        "status": "drift_detected" if changes else "no_drift",
        "changes": changes,
        "ai_explanation": ai_explanation,
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Simulate first run
    import sys
    sys.path.insert(0, "include/src")
    from extract import extract

    df = extract("include/data/raw/customers.csv")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")

    report = detect_drift(df, source_name="customers", run_id=run_id)
    print("\n--- Drift Report ---")
    print(f"Status   : {report['status']}")
    print(f"Changes  : {report['changes']}")
    print(f"AI Explaination   : {report['ai_explanation']}")