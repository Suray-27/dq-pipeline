import os
import pandas as pd

def extract(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    print(f"[Extract] Loaded {len(df)} rows, {len(df.columns)} columns from: {path}")
    return df

if __name__ == "__main__":
    from config import SOURCES
    
    print("--- Testing Ingestion For All Configured Sources ---")
    for source_name, source_info in SOURCES.items():
        print(f"\nExtracting {source_name}...")
        df = extract(source_info["file"])
        print(df.head(2))