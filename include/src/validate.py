import os
import json
import pandas as pd
from datetime import datetime
from config import get_engine

# 1. DEFINE ALL CHECK FUNCTIONS FIRST
def check_not_null(df, col, params):
    mask = df[col].isna() | (df[col].astype(str).str.strip() == "nan")
    return mask, f"{col} is null"

def check_unique(df, col, params):
    mask = df[col].duplicated(keep=False) & df[col].notna()
    return mask, f"{col} has duplicate value"

def check_in_range(df, col, params):
    lo, hi = params["min"], params["max"]
    numeric_col = pd.to_numeric(df[col], errors="coerce")
    mask = numeric_col.notna() & ((numeric_col < lo) | (numeric_col > hi))
    return mask, f"{col} outside range [{lo}, {hi}]"

def check_valid_date(df, col, params):
    fmt = params.get("format", "%Y-%m-%d")
    def is_invalid(v):
        if pd.isna(v): return False
        try:
            datetime.strptime(str(v), fmt)
            return False
        except ValueError:
            return True
    mask = df[col].apply(is_invalid)
    return mask, f"{col} is not a valid date"

def check_min_date(df, col, params):
    min_val = datetime.strptime(params["min"], "%Y-%m-%d")
    def is_too_old(v):
        if pd.isna(v): return False
        try:
            d = datetime.strptime(str(v)[:10], "%Y-%m-%d")
            return d < min_val
        except ValueError:
            return False
    mask = df[col].apply(is_too_old)
    return mask, f"{col} is before minimum date {params['min']}"

def check_max_date(df, col, params):
    fmt = params.get("format", "%Y-%m-%d")
    max_val = datetime.today() if params.get("max") == "today" else \
        datetime.strptime(params["max"], "%Y-%m-%d")
    def is_future(v):
        if pd.isna(v): return False
        try:
            d = datetime.strptime(str(v)[:10], "%Y-%m-%d")
            return d > max_val
        except ValueError:
            return False
    mask = df[col].apply(is_future)
    return mask, f"{col} is a future date"

def check_regex(df, col, params):
    pattern = params["pattern"]
    mask = df[col].notna() & ~df[col].astype(str).str.match(pattern)
    return mask, f"{col} does not match pattern"

def check_allowed_values(df, col, params):
    allowed = set(params["values"])
    mask = df[col].notna() & ~df[col].isin(allowed)
    return mask, f"{col} not in allowed values {sorted(allowed)}"

def check_referential_integrity(df, col, params):
    ref_table = params["reference_table"]
    ref_col = params["reference_column"]
    try:
        engine = get_engine()
        # REMOVE the double quotes around table and column names
        query = f'SELECT {ref_col} FROM {ref_table}'
        ref_df = pd.read_sql(query, engine)
        
        # Normalize to account for Snowflake's uppercase output
        valid_ids = set(ref_df.iloc[:, 0].dropna().unique())
        mask = df[col].notna() & ~df[col].isin(valid_ids)
    except Exception as e:
        print(f"[Validate] Referential check failed: {e}")
        mask = pd.Series(False, index=df.index)
    return mask, f"{col} references non-existent record in {ref_table}"

def check_refund_amount(df, col, params):
    if "status" not in df.columns:
        return pd.Series(False, index=df.index), ""
    mask = (df["status"] == "refunded") & (df[col] > 0)
    return mask, f"refunded transaction has positive {col}"


# 2. DEFINE DISPATCH DICTIONARY AFTER ALL FUNCTIONS ARE DECLARED
RULE_DISPATCH = {
    "not_null": check_not_null,
    "unique": check_unique,
    "in_range": check_in_range,
    "valid_date": check_valid_date,
    "max_date": check_max_date,
    "min_date": check_min_date,
    "regex": check_regex,
    "allowed_values": check_allowed_values,
    "refund_check": check_refund_amount,
    "referential_integrity": check_referential_integrity,
}


# 3. CORE VALIDATION RUNNER
def validate(df: pd.DataFrame, rules: list) -> tuple:
    df = df.reset_index(drop=True)
    violation_mask = pd.Series(False, index=df.index)
    violation_records = []

    for rule in rules:
        col = rule["column"]
        rule_type = rule["rule_type"]
        params = rule.get("params", {})

        if col not in df.columns:
            continue

        checker = RULE_DISPATCH.get(rule_type)
        if checker is None:
            continue

        mask, msg = checker(df, col, params)
        violation_mask |= mask

        for idx in df.index[mask]:
            violation_records.append({
                "row_index": int(idx),
                "id": df.loc[idx].get("id"),
                "column_name": col,
                "rule_type": rule_type,
                "message": msg,
                "value": str(df.loc[idx, col]),
                "reasoning": rule.get("reasoning", ""),
            })

    passed_df = df[~violation_mask]
    failed_df = df[violation_mask]
    return passed_df, failed_df, violation_records


if __name__ == "__main__":
    import sys
    SRC_DIR = os.environ.get("SRC_DIR", "include/src")
    RAW_CUSTOMERS_PATH = os.environ.get("RAW_CUSTOMERS_PATH", "data/raw/customers.csv")
    RULES_FILE_PATH = os.environ.get("RULES_FILE_PATH", "data/rules.json")
    VIOLATIONS_FILE_PATH = os.environ.get("VIOLATIONS_FILE_PATH", "data/violations.json")

    sys.path.insert(0, SRC_DIR)
    from extract import extract
    from transform import transform

    df = extract(RAW_CUSTOMERS_PATH)
    df = transform(df)

    if os.path.exists(RULES_FILE_PATH):
        with open(RULES_FILE_PATH) as f:
            rules = json.load(f)
    else:
        rules = []

    passed, failed, violations = validate(df, rules)