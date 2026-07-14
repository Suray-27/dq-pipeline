import os
from dotenv import load_dotenv
from snowflake.sqlalchemy import URL
from sqlalchemy import create_engine, text
import pandas as pd
import json
from datetime import datetime
load_dotenv()


# ─── Snowflake Connection ──────────────────────────────────────
def get_engine():
    return create_engine(URL(
        account=os.environ.get("SNOWFLAKE_ACCOUNT"),
        user=os.environ.get("SNOWFLAKE_USER"),
        password=os.environ.get("SNOWFLAKE_PASSWORD"),
        database=os.environ.get("SNOWFLAKE_DATABASE"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
    ))


# ─── Source Tables ─────────────────────────────────────────────
SOURCES = {
    "customers": {
        "file": "include/data/raw/customers.csv",
        "curated": "curated_customers",
        "quarantine": "quarantine_customers",
        "depends_on": [],
        "validates_against": [],
    },
    "transactions": {
        "file": "include/data/raw/transactions.csv",
        "curated": "curated_transactions",
        "quarantine": "quarantine_transactions",
        "depends_on": [],
        "validates_against": ["curated_customers"],
    },
}


# ─── Snowflake Table Names ─────────────────────────────────────
TABLES = {
    "violations":    "dq_violations",
    "fixes":         "dq_fix_suggestions",
    "summaries":     "dq_run_summaries",
    "drift":         "dq_drift_reports",
    "lineage":       "data_lineage",
    "schema_reg":    "schema_registry",
    "root_cause":    "dq_root_cause_analysis",
    "metadata":      "pipeline_metadata",
    "control":       "pipeline_control",
}


# ─── Metadata (replaces local files) ──────────────────────────
def get_metadata(source_name: str, key: str) -> str:
    """Read latest metadata value for a source."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT METADATA_VALUE 
                FROM {TABLES["metadata"]}
                WHERE SOURCE_NAME = '{source_name}'
                AND METADATA_KEY = '{key}'
                ORDER BY UPDATED_AT DESC
                LIMIT 1
            """))
            row = result.fetchone()
            return row[0] if row else ""
    except Exception:
        return ""


def set_metadata(
    source_name: str,
    key: str,
    value: str,
    pipeline_run_id: str = "",
    source_run_id: str = "",
):
    """Write metadata with run tracking."""
    engine = get_engine()
    pd.DataFrame([{
        "pipeline_run_id": pipeline_run_id,
        "source_run_id": source_run_id or f"{pipeline_run_id}_{source_name}",
        "source_name": source_name,
        "metadata_key": key,
        "metadata_value": value,
        "updated_at": datetime.now().isoformat(),
    }]).to_sql(
        TABLES["metadata"], engine,
        if_exists="append", index=False
    )


def set_metadata(source_name: str, key: str, value: str):
    """Write metadata to Snowflake instead of local files."""
    engine = get_engine()
    pd.DataFrame([{
        "source_name": source_name,
        "metadata_key": key,
        "metadata_value": value,
        "updated_at": datetime.now().isoformat(),
    }]).to_sql(TABLES["metadata"], engine, if_exists="append", index=False)


# ─── Pipeline Control ──────────────────────────────────────────
def get_active_sources() -> dict:
    """
    Read pipeline control table to determine which sources to process.
    Falls back to all SOURCES if control table doesn't exist yet.
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT SOURCE_NAME, IS_ACTIVE, LOAD_MODE, PRIORITY
                FROM {TABLES["control"]}
                WHERE IS_ACTIVE = TRUE
                ORDER BY PRIORITY ASC
            """))
            rows = result.fetchall()
            if not rows:
                return SOURCES

            active = {}
            for row in rows:
                source_name = row[0].lower()
                if source_name in SOURCES:
                    active[source_name] = {
                        **SOURCES[source_name],
                        "load_mode": row[2],
                        "priority": row[3],
                    }
            return active
    except Exception:
        print("[Config] Pipeline control table not found — using all sources")
        return SOURCES


def initialize_control_table():
    """Create pipeline control table with default settings."""
    engine = get_engine()
    records = []
    for i, (source_name, source) in enumerate(SOURCES.items(), 1):
        records.append({
            "source_name": source_name,
            "is_active": True,
            "load_mode": "full",
            "priority": i,
            "updated_at": datetime.now().isoformat(),
        })
    pd.DataFrame(records).to_sql(
        TABLES["control"], engine,
        if_exists="replace", index=False
    )
    print(f"[Config] Pipeline control table initialized with {len(records)} sources")


def initialize_metadata_table():
    """Create metadata table if it doesn't exist."""
    engine = get_engine()
    pd.DataFrame([{
        "source_name": "system",
        "metadata_key": "initialized",
        "metadata_value": "true",
        "updated_at": datetime.now().isoformat(),
    }]).to_sql(
        TABLES["metadata"], engine,
        if_exists="replace", index=False
    )
    print("[Config] Metadata table initialized")


if __name__ == "__main__":
    print("Initializing Snowflake control tables...")
    initialize_metadata_table()
    initialize_control_table()
    print("\nActive sources:")
    for name, source in get_active_sources().items():
        print(f"  {name} → mode: {source.get('load_mode')} priority: {source.get('priority')}")