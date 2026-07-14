import os
import pandas as pd

def transform(df: pd.DataFrame, source_name: str = "unknown") -> pd.DataFrame:
    df = df.copy()

    # Generic clean: Trim whitespace on all string columns
    str_cols = df.select_dtypes(include="object").columns
    for col in str_cols:
        df[col] = df[col].str.strip()

    # Source-Specific Transform Logic
    if source_name == "customers" and "status" in df.columns:
        df["status"] = df["status"].str.lower()
    elif source_name == "transactions" and "status" in df.columns:
        df["status"] = df["status"].str.lower()

    print(f"[Transform] Cleaned {len(df)} rows for source: {source_name}")
    return df

if __name__ == "__main__":
    import sys
    SRC_DIR = os.environ.get("SRC_DIR", "include/src")
    sys.path.insert(0, SRC_DIR)
    from extract import extract
    from config import SOURCES

    print("--- Testing Transformation For All Configured Sources ---")
    for source_name, source_info in SOURCES.items():
        df = extract(source_info["file"])
        df = transform(df, source_name=source_name)