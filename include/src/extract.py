import pandas as pd

def extract(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    print(f"[Extract] Loaded {len(df)} rows, {len(df.columns)} columns")
    print(f"[Extract] Columns: {list(df.columns)}")
    print(f"[Extract] Dtypes:\n{df.dtypes}")
    return df

if __name__ == "__main__":
    df = extract("data/raw/customers.csv")
    print("\n--- Preview ---")
    print(df)