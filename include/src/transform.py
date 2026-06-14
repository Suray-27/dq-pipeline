import pandas as pd


def transform(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Trim whitespace on all string columns
    str_cols = df.select_dtypes(include="object").columns
    for col in str_cols:
        df[col] = df[col].str.strip()

    # Normalize status to lowercase
    if "status" in df.columns:
        df["status"] = df["status"].str.lower()

    print(f"[Transform] Cleaned {len(df)} rows")
    return df


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "include/src")
    from extract import extract

    df = extract("data/raw/customers.csv")
    print("\n--- Before Transform ---")
    print(df["status"])

    df = transform(df)
    print("\n--- After Transform ---")
    print(df["status"])