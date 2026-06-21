import json
import os
import sys
import hashlib
sys.path.insert(0, "include/src")

from extract import extract
from ai_rules import infer_rules
from transform import transform
from validate import validate
from ai_fixes import analyze_failures
from ai_summary import generate_summary
from ai_drift import detect_drift
from lineage import write_lineage
from load import load
import pandas as pd
import sqlalchemy
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()


def get_file_hash(filepath: str) -> str:
    """Generate MD5 hash of file contents."""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def get_cached_file_hash(source_name: str) -> str:
    """Load previously saved file hash."""
    hash_path = f"include/data/.file_hash_{source_name}.txt"
    try:
        with open(hash_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def save_file_hash(source_name: str, file_hash: str):
    """Save current file hash for next run comparison."""
    hash_path = f"include/data/.file_hash_{source_name}.txt"
    with open(hash_path, "w") as f:
        f.write(file_hash)


def has_new_data(source_name: str, filepath: str) -> bool:
    """Check if source file has changed since last run."""
    current_hash = get_file_hash(filepath)
    cached_hash = get_cached_file_hash(source_name)

    if current_hash == cached_hash:
        print(f"[Pipeline] No new data in '{source_name}' — skipping")
        return False

    print(f"[Pipeline] New data detected in '{source_name}' — processing")
    save_file_hash(source_name, current_hash)
    return True


def process_table(
    source_name: str,
    source_file: str,
    destination_curated: str,
    destination_quarantine: str,
    depends_on: list,
    run_id: str,
):
    # Level 1 — check file change
    if not has_new_data(source_name, source_file):
        return None

    # Extract
    df = extract(source_file)

    # Level 2 — schema hash controls Groq (handled inside infer_rules)
    rules = infer_rules(df, source_name=source_name)

    # Transform
    df_clean = transform(df)

    # Validate
    passed, failed, violations = validate(df_clean, rules)

    # Level 3 — skip AI if no violations
    if violations:
        print(f"[Pipeline] {len(violations)} violations found — calling AI fixes...")
        fixes = analyze_failures(violations)
    else:
        print(f"[Pipeline] No violations found — skipping AI fixes")
        fixes = []

    # Load
    load(passed, failed, violations, fixes)

    # Write lineage
    write_lineage(
        run_id=run_id,
        source_name=source_name,
        source_file=source_file,
        total_records=len(df),
        passed_records=len(passed),
        failed_records=len(failed),
        destination_curated=destination_curated,
        destination_quarantine=destination_quarantine,
        depends_on=depends_on,
        rules_applied=len(rules),
        violations_found=len(violations),
    )

    return {
        "df": df,
        "passed": passed,
        "failed": failed,
        "violations": violations,
        "fixes": fixes,
    }


def run():
    print("\n========== DQ PIPELINE STARTED ==========\n")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    print(f"[Pipeline] Run ID: {run_id}")

    results = {}

    # ── CUSTOMERS ──────────────────────────────────────────────
    print("\n--- Checking: customers ---")
    result_c = process_table(
        source_name="customers",
        source_file="include/data/raw/customers.csv",
        destination_curated="curated_customers",
        destination_quarantine="quarantine_customers",
        depends_on=[],
        run_id=run_id,
    )
    if result_c:
        results["customers"] = result_c

    # ── TRANSACTIONS ───────────────────────────────────────────
    print("\n--- Checking: transactions ---")
    result_t = process_table(
        source_name="transactions",
        source_file="include/data/raw/transactions.csv",
        destination_curated="curated_transactions",
        destination_quarantine="quarantine_transactions",
        depends_on=["curated_customers"],
        run_id=run_id,
    )
    if result_t:
        results["transactions"] = result_t

    # ── Check if anything ran ──────────────────────────────────
    if not results:
        print("\n[Pipeline] No new data in any source — pipeline skipped")
        print("========== DQ PIPELINE SKIPPED ==========\n")
        return

    # ── AI SUMMARY (only if something ran) ────────────────────
    all_violations = []
    all_fixes = []
    total_passed = 0
    total_failed = 0

    for r in results.values():
        all_violations += r["violations"]
        all_fixes += r["fixes"]
        total_passed += len(r["passed"])
        total_failed += len(r["failed"])

    summary = generate_summary(total_passed, total_failed, all_violations, all_fixes)

    # ── DRIFT DETECTION ────────────────────────────────────────
    DB_URL = os.environ.get("DB_URL_VAR")
    engine = sqlalchemy.create_engine(DB_URL)

    pd.DataFrame([summary]).to_sql(
        "dq_run_summaries", engine,
        if_exists="append", index=False
    )

    for source_name, result in results.items():
        drift = detect_drift(result["df"], source_name=source_name, run_id=run_id)
        pd.DataFrame([{
            "source_name": drift["source_name"],
            "run_id": drift["run_id"],
            "status": drift["status"],
            "changes": json.dumps(drift["changes"]),
            "ai_explanation": drift["ai_explanation"],
        }]).to_sql(
            "dq_drift_reports", engine,
            if_exists="append", index=False
        )

    print("\n========== DQ PIPELINE COMPLETED ==========\n")
    for source, r in results.items():
        print(f"{source:15} → {len(r['passed'])} curated, {len(r['failed'])} quarantined")
    print(f"Total violations : {len(all_violations)}")
    print(f"Run ID           : {run_id}")


if __name__ == "__main__":
    run()