import json
import os
import sys
import hashlib
sys.path.insert(0, "include/src")

from ai_rootcause import analyze_root_causes
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
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def get_cached_file_hash(source_name: str) -> str:
    hash_path = f"include/data/.file_hash_{source_name}.txt"
    try:
        with open(hash_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def save_file_hash(source_name: str, file_hash: str):
    hash_path = f"include/data/.file_hash_{source_name}.txt"
    with open(hash_path, "w") as f:
        f.write(file_hash)


def has_new_data(source_name: str, filepath: str) -> bool:
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
    if not has_new_data(source_name, source_file):
        return None

    df = extract(source_file)
    rules = infer_rules(df, source_name=source_name)
    df_clean = transform(df)
    passed, failed, violations = validate(df_clean, rules)

    if violations:
        print(f"[Pipeline] {len(violations)} violations found — calling AI fixes...")
        fixes = analyze_failures(violations)
    else:
        print(f"[Pipeline] No violations found — skipping AI fixes")
        fixes = []

    load(passed, failed, violations, fixes)

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

    # ── Aggregate results ──────────────────────────────────────
    all_violations = []
    all_fixes = []
    total_passed = 0
    total_failed = 0

    for r in results.values():
        all_violations += r["violations"]
        all_fixes += r["fixes"]
        total_passed += len(r["passed"])
        total_failed += len(r["failed"])

    # ── DB Engine ──────────────────────────────────────────────
    DB_URL = os.environ.get("DB_URL_VAR")
    engine = sqlalchemy.create_engine(DB_URL)

    # ── AI SUMMARY ─────────────────────────────────────────────
    if all_violations:
        print(f"[Pipeline] Generating AI summary...")
        summary = generate_summary(total_passed, total_failed, all_violations, all_fixes)
        pd.DataFrame([summary]).to_sql(
            "dq_run_summaries", engine,
            if_exists="append", index=False
        )
    else:
        print("[Pipeline] No violations — skipping AI summary")

    # ── ROOT CAUSE ANALYSIS ────────────────────────────────────
    if all_violations:
        print("\n[Pipeline] Running cross-table root cause analysis...")
        tables_for_rca = {
            source: {
                "total_records": len(r["passed"]) + len(r["failed"]),
                "passed_count": len(r["passed"]),
                "failed_count": len(r["failed"]),
                "violations": r["violations"],
            }
            for source, r in results.items()
        }

        rca = analyze_root_causes(
            tables_for_rca,
            dependencies={"transactions": ["curated_customers"]}
        )

        pd.DataFrame([{
            "run_id": run_id,
            "overall_health": rca["overall_health"],
            "executive_summary": rca["executive_summary"],
            "root_causes": json.dumps(rca["root_causes"]),
            "cross_table_impacts": json.dumps(rca["cross_table_impacts"]),
            "priority_fixes": json.dumps(rca["priority_fixes"]),
            "systemic_recommendations": json.dumps(rca["systemic_recommendations"]),
            "captured_at": datetime.now().isoformat(),
        }]).to_sql(
            "dq_root_cause_analysis", engine,
            if_exists="append", index=False
        )
        print(f"[Pipeline] Root cause saved — health: {rca['overall_health']}")

    # ── DRIFT DETECTION ────────────────────────────────────────
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