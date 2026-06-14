import pandas as pd
import os
import json
from datetime import datetime
from sqlalchemy import create_engine

DB_URL = os.environ.get("DB_URL_VAR", "")

def get_engine():
    return create_engine(DB_URL)


def load(passed_df: pd.DataFrame, failed_df: pd.DataFrame,
         violations: list, fixes: list):

    engine = get_engine()

    passed_df.to_sql("curated_customers", engine,
                     if_exists="replace", index=False)
    print(f"[Load] curated_customers: {len(passed_df)} rows")

    failed_df.to_sql("quarantine_customers", engine,
                     if_exists="replace", index=False)
    print(f"[Load] quarantine_customers: {len(failed_df)} rows")

    pd.DataFrame(violations).to_sql("dq_violations", engine,
                                    if_exists="replace", index=False)
    print(f"[Load] dq_violations: {len(violations)} rows")

    if fixes:
        pd.DataFrame(fixes).to_sql("dq_fix_suggestions", engine,
                                   if_exists="replace", index=False)
        print(f"[Load] dq_fix_suggestions: {len(fixes)} rows")

    engine.dispose()
    print("[Load] Done — all tables written to PostgreSQL")

def save_drift_report(report: dict):
    engine = get_engine()
    pd.DataFrame([{
        "source_name": report["source_name"],
        "run_id": report["run_id"],
        "status": report["status"],
        "changes": json.dumps(report["changes"]),
        "ai_explanation": report["ai_explanation"],
        "captured_at": datetime.now().isoformat(),
    }]).to_sql(
        "dq_drift_reports", engine,
        if_exists="append", index=False
    )
    print(f"[Load] Saved drift report — status: {report['status']}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "include/src")
    from extract import extract
    from transform import transform
    from validate import validate

    df = extract("data/raw/customers.csv")
    df = transform(df)

    with open("data/rules.json") as f:
        rules = json.load(f)

    passed, failed, violations = validate(df, rules)

    with open("data/fix_suggestions.json") as f:
        fixes = json.load(f)

    load(passed, failed, violations, fixes)