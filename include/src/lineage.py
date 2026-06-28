import os
import json
import pandas as pd
from datetime import datetime
from config import get_engine, TABLES


def write_lineage(
    run_id: str,
    source_name: str,
    source_file: str,
    total_records: int,
    passed_records: int,
    failed_records: int,
    destination_curated: str,
    destination_quarantine: str,
    depends_on: list = None,
    rules_applied: int = 0,
    violations_found: int = 0,
):
    outcome = (
        "success" if failed_records == 0
        else "partial" if passed_records > 0
        else "failed"
    )

    record = {
        "lineage_id": f"{run_id}_{source_name}",
        "run_id": run_id,
        "source_name": source_name,
        "source_file": source_file,
        "captured_at": datetime.now().isoformat(),
        "total_records": total_records,
        "passed_records": passed_records,
        "failed_records": failed_records,
        "pass_rate": round(passed_records / total_records * 100, 1) if total_records > 0 else 0,
        "outcome": outcome,
        "destination_curated": destination_curated,
        "destination_quarantine": destination_quarantine,
        "depends_on": json.dumps(depends_on or []),
        "rules_applied": rules_applied,
        "violations_found": violations_found,
    }

    engine = get_engine()
    pd.DataFrame([record]).to_sql(
        TABLES["lineage"], engine,
        if_exists="append", index=False
    )
    print(f"[Lineage] Written for '{source_name}' — run_id: {run_id} — outcome: {outcome}")
    return record


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Test with mock data
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")

    # Customers lineage
    write_lineage(
        run_id=run_id,
        source_name="customers",
        source_file="include/data/raw/customers.csv",
        total_records=9,
        passed_records=3,
        failed_records=6,
        destination_curated="curated_customers",
        destination_quarantine="quarantine_customers",
        depends_on=[],
        rules_applied=9,
        violations_found=6,
    )

    # Transactions lineage
    write_lineage(
        run_id=run_id,
        source_name="transactions",
        source_file="include/data/raw/transactions.csv",
        total_records=10,
        passed_records=2,
        failed_records=8,
        destination_curated="curated_transactions",
        destination_quarantine="quarantine_transactions",
        depends_on=["curated_customers"],
        rules_applied=9,
        violations_found=13,
    )