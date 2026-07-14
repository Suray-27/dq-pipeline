from config import get_engine, SOURCES, TABLES
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
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()


def get_file_hash(filepath: str) -> str:
    with open(filepath, "rb") as f:
        import hashlib
        return hashlib.md5(f.read()).hexdigest()


def get_cached_file_hash(source_name: str) -> str:
    from config import get_metadata
    return get_metadata(source_name, "file_hash")


def save_file_hash(source_name: str, file_hash: str):
    from config import set_metadata
    set_metadata(source_name, "file_hash", file_hash)


def has_new_data(source_name: str, filepath: str,
                 pipeline_run_id: str = "") -> bool:
    current_hash = get_file_hash(filepath)
    cached_hash = get_cached_file_hash(source_name)

    if current_hash == cached_hash:
        print(f"[Pipeline] No new data in '{source_name}' — skipping")
        return False

    print(f"[Pipeline] New data detected in '{source_name}' — processing")
    # Save file hash with run tracking
    from config import set_metadata
    source_run_id = f"{pipeline_run_id}_{source_name}"
    set_metadata(source_name, "file_hash", current_hash,
                 pipeline_run_id, source_run_id)
    return True


def process_table(source_name: str, run_id: str):
    source = SOURCES[source_name]
    source_file = source["file"]
    source_run_id = f"{run_id}_{source_name}"

    if not has_new_data(source_name, source_file, pipeline_run_id=run_id):
        return None

    df = extract(source_file)

    # Pass run IDs to rule inference
    rules = infer_rules(
        df,
        source_name=source_name,
        pipeline_run_id=run_id,
        source_run_id=source_run_id,
    )

    df_clean = transform(df)
    passed, failed, violations = validate(df_clean, rules)

    if violations:
        print(f"[Pipeline] {len(violations)} violations — calling AI fixes...")
        fixes = analyze_failures(violations)
    else:
        print(f"[Pipeline] No violations — skipping AI fixes")
        fixes = []

    load(passed, failed, violations, fixes, source_name=source_name)

    write_lineage(
        run_id=run_id,
        source_name=source_name,
        source_file=source_file,
        total_records=len(df),
        passed_records=len(passed),
        failed_records=len(failed),
        destination_curated=source["curated"],
        destination_quarantine=source["quarantine"],
        depends_on=source.get("validates_against", []),
        rules_applied=len(rules),
        violations_found=len(violations),
    )

    return {
        "df": df,
        "passed": passed,
        "failed": failed,
        "violations": violations,
        "fixes": fixes,
        "source_run_id": source_run_id,
    }


def run():
    print("\n========== DQ PIPELINE STARTED ==========\n")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    print(f"[Pipeline] Run ID: {run_id}")

    from config import get_active_sources
    active_sources = get_active_sources()
    print(f"[Pipeline] Active sources: {list(active_sources.keys())}")

    results = {}
    for source_name in active_sources:
        print(f"\n--- Checking: {source_name} ---")
        result = process_table(source_name, run_id)
        if result:
            results[source_name] = result

    if not results:
        print("\n[Pipeline] No new data — pipeline skipped")
        print("========== DQ PIPELINE SKIPPED ==========\n")
        return

    # Aggregate all violations for cross-table AI steps
    all_violations = []
    total_passed = 0
    total_failed = 0

    for r in results.values():
        all_violations += r["violations"]
        total_passed += len(r["passed"])
        total_failed += len(r["failed"])

    engine = get_engine()

    # AI Summary — only after all tables (needs full picture)
    if all_violations:
        print("\n[Pipeline] Generating AI summary...")
        summary = generate_summary(total_passed, total_failed, all_violations, [])
        pd.DataFrame([summary]).to_sql(
            TABLES["summaries"], engine,
            if_exists="append", index=False
        )

    # Root Cause Analysis — only after all tables (cross-table patterns)
    if all_violations and len(results) > 0:
        print("[Pipeline] Running cross-table root cause analysis...")
        tables_for_rca = {
            source: {
                "total_records": len(r["passed"]) + len(r["failed"]),
                "passed_count": len(r["passed"]),
                "failed_count": len(r["failed"]),
                "violations": r["violations"],
            }
            for source, r in results.items()
        }
        dependencies = {
            s: SOURCES[s].get("validates_against", [])
            for s in results
            if SOURCES[s].get("validates_against")
        }
        rca = analyze_root_causes(tables_for_rca, dependencies)
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
            TABLES["root_cause"], engine,
            if_exists="append", index=False
        )
        print(f"[Pipeline] RCA saved — health: {rca['overall_health']}")

    # Drift Detection — per table after all processing
    for source_name, result in results.items():
        drift = detect_drift(result["df"], source_name=source_name, run_id=run_id)
        pd.DataFrame([{
            "source_name": drift["source_name"],
            "run_id": drift["run_id"],
            "status": drift["status"],
            "changes": json.dumps(drift["changes"]),
            "ai_explanation": drift["ai_explanation"],
            "captured_at": datetime.now().isoformat(),
        }]).to_sql(
            TABLES["drift"], engine,
            if_exists="append", index=False
        )

    print("\n========== DQ PIPELINE COMPLETED ==========\n")
    for source, r in results.items():
        print(f"{source:15} → {len(r['passed'])} curated, {len(r['failed'])} quarantined")
    print(f"Total violations : {len(all_violations)}")
    print(f"Run ID           : {run_id}")


if __name__ == "__main__":
    run()