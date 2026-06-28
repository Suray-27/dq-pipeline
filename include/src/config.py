import os
from dotenv import load_dotenv
from snowflake.sqlalchemy import URL
from sqlalchemy import create_engine
load_dotenv()


# ─── Snowflake Connection ──────────────────────────────────────
def get_engine():
    """Single engine factory used by all modules."""
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
    },
    "transactions": {
        "file": "include/data/raw/transactions.csv",
        "curated": "curated_transactions",
        "quarantine": "quarantine_transactions",
        "depends_on": ["curated_customers"],
    },
}


# ─── File Paths ────────────────────────────────────────────────
BUSINESS_RULES_PATH = "include/data/business_rules.json"
RULES_CACHE_DIR     = "include/data"
HASH_DIR            = "include/data"


def get_rules_path(source_name: str) -> str:
    return f"{RULES_CACHE_DIR}/rules_{source_name}.json"


def get_file_hash_path(source_name: str) -> str:
    return f"{HASH_DIR}/.file_hash_{source_name}.txt"


def get_schema_hash_path(source_name: str) -> str:
    return f"{HASH_DIR}/.schema_hash_{source_name}.txt"


# ─── Snowflake Table Names ─────────────────────────────────────
TABLES = {
    "violations":    "DQ_VIOLATIONS",
    "fixes":         "DQ_FIX_SUGGESTIONS",
    "summaries":     "DQ_RUN_SUMMARIES",
    "drift":         "DQ_DRIFT_REPORTS",
    "lineage":       "DATA_LINEAGE",
    "schema_reg":    "SCHEMA_REGISTRY",
    "root_cause":    "DQ_ROOT_CAUSE_ANALYSIS",
}