import pandas as pd
import json
from datetime import datetime


def check_not_null(df, col, params):
    mask = df[col].isna()
    return mask, f"{col} is null"


def check_unique(df, col, params):
    mask = df[col].duplicated(keep=False) & df[col].notna()
    return mask, f"{col} has duplicate value"


def check_in_range(df, col, params):
    lo, hi = params["min"], params["max"]
    mask = df[col].notna() & ((df[col] < lo) | (df[col] > hi))
    return mask, f"{col} outside range [{lo}, {hi}]"


def check_valid_date(df, col, params):
    fmt = params.get("format", "%Y-%m-%d")

    def is_invalid(v):
        if pd.isna(v):
            return False
        try:
            datetime.strptime(str(v), fmt)
            return False
        except ValueError:
            return True

    mask = df[col].apply(is_invalid)
    return mask, f"{col} is not a valid date"


def check_max_date(df, col, params):
    fmt = params.get("format", "%Y-%m-%d")
    max_val = datetime.today() if params.get("max") == "today" else \
        datetime.strptime(params["max"], fmt)

    def is_future(v):
        if pd.isna(v):
            return False
        try:
            return datetime.strptime(str(v), fmt) > max_val
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

RULE_DISPATCH = {
    "not_null": check_not_null,
    "unique": check_unique,
    "in_range": check_in_range,
    "valid_date": check_valid_date,
    "max_date": check_max_date,
    "regex": check_regex,
    "allowed_values": check_allowed_values,
}


def validate(df: pd.DataFrame, rules: list) -> tuple:
    df = df.reset_index(drop=True)
    violation_mask = pd.Series(False, index=df.index)
    violation_records = []

    for rule in rules:
        col = rule["column"]
        rule_type = rule["rule_type"]
        params = rule.get("params", {})

        if col not in df.columns:
            print(f"[Validate] WARNING: column '{col}' not found, skipping")
            continue

        checker = RULE_DISPATCH.get(rule_type)
        if checker is None:
            print(f"[Validate] WARNING: unknown rule '{rule_type}', skipping")
            continue

        mask, msg = checker(df, col, params)
        violation_mask |= mask

        for idx in df.index[mask]:
            violation_records.append({
                "row_index": int(idx),
                "id": df.loc[idx].get("id"),
                "column": col,
                "rule_type": rule_type,
                "message": msg,
                "value": str(df.loc[idx, col]),
                "reasoning": rule.get("reasoning", ""),
            })

    passed_df = df[~violation_mask]
    failed_df = df[violation_mask]

    print(f"[Validate] {len(passed_df)} passed, {len(failed_df)} failed")
    print(f"[Validate] {len(violation_records)} total violations found")

    return passed_df, failed_df, violation_records


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "include/src")
    from extract import extract
    from transform import transform

    df = extract("data/raw/customers.csv")
    df = transform(df)

    with open("data/rules.json") as f:
        rules = json.load(f)

    passed, failed, violations = validate(df, rules)

    print("\n--- PASSED ROWS ---")
    print(passed)

    print("\n--- FAILED ROWS ---")
    print(failed)

    print("\n--- VIOLATIONS ---")
    for v in violations:
        print(f"  Row {v['row_index']} | {v['column']} | {v['rule_type']} | value: {v['value']}")

    with open("data/violations.json", "w") as f:
        json.dump(violations, f, indent=2, default=str)
    print("\n[Validate] Saved violations to data/violations.json")