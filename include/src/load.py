import pandas as pd
import json
import os
import sqlalchemy
from datetime import datetime
from config import get_engine, TABLES, SOURCES


def load(
    passed_df: pd.DataFrame,
    failed_df: pd.DataFrame,
    violations: list,
    fixes: list,
    source_name: str = "unknown",
):
    engine = get_engine()
    now = datetime.now().isoformat()

    # Get table names from config
    curated_table = SOURCES.get(source_name, {}).get("curated", f"curated_{source_name}")
    quarantine_table = SOURCES.get(source_name, {}).get("quarantine", f"quarantine_{source_name}")

    # Add timestamp to curated and quarantine
    passed_df = passed_df.copy()
    failed_df = failed_df.copy()
    passed_df["captured_at"] = now
    failed_df["captured_at"] = now

    passed_df.to_sql(curated_table, engine, if_exists="replace", index=False)
    print(f"[Load] {curated_table}: {len(passed_df)} rows")

    failed_df.to_sql(quarantine_table, engine, if_exists="replace", index=False)
    print(f"[Load] {quarantine_table}: {len(failed_df)} rows")

    if violations:
        violations_df = pd.DataFrame(violations)
        violations_df["captured_at"] = now
        violations_df = violations_df.rename(columns={"column": "column_name"})
        violations_df.to_sql(
            TABLES["violations"], engine,
            if_exists="append", index=False
        )
        print(f"[Load] {TABLES['violations']}: {len(violations_df)} rows")

    if fixes:
        fixes_df = pd.DataFrame(fixes)
        fixes_df["captured_at"] = now
        fixes_df.to_sql(
            TABLES["fixes"], engine,
            if_exists="append", index=False
        )
        print(f"[Load] {TABLES['fixes']}: {len(fixes_df)} rows")

    engine.dispose()
    print(f"[Load] Done — {source_name}")