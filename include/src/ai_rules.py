import json
import os
import requests
import pandas as pd


def _call_groq(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=body,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


PROMPT_TEMPLATE = """You are a data quality engineer.
Given this schema and sample rows, propose data quality rules as a JSON array.

Each rule must have:
- "column": column name
- "rule_type": one of [not_null, unique, in_range, valid_date, max_date, regex, allowed_values]
- "params": dict of parameters needed for that rule type
- "reasoning": short explanation of why this rule makes sense

Rule type param formats:
- not_null: {{}}
- unique: {{}}
- in_range: {{"min": x, "max": y}}
- valid_date: {{"format": "%Y-%m-%d"}}
- max_date: {{"format": "%Y-%m-%d", "max": "today"}}
- regex: {{"pattern": "..."}}
- allowed_values: {{"values": [...]}}

Table: {source_name}
Description: {description}

Schema:
{schema}

Sample rows (JSON):
{sample}

Note: Do NOT infer rules for columns that already have business rules defined:
{existing_rule_columns}

Respond with ONLY the JSON array, no other text, no markdown fences.
"""


def load_business_rules(source_name: str, config_path: str = "include/data/business_rules.json") -> list:
    """Load predefined business rules for a specific table."""
    try:
        with open(config_path) as f:
            config = json.load(f)
        rules = config.get(source_name, {}).get("rules", [])
        print(f"[AI Rules] Loaded {len(rules)} business rules for '{source_name}'")
        return rules
    except FileNotFoundError:
        print(f"[AI Rules] No business rules config found at {config_path}")
        return []


def infer_rules(df: pd.DataFrame, source_name: str = "unknown") -> list:
    """Infer rules using Groq + merge with business config rules."""

    # Load business rules first
    business_rules = load_business_rules(source_name)
    existing_rule_columns = list({r["column"] for r in business_rules})

    # Load description from config
    try:
        with open("include/data/business_rules.json") as f:
            config = json.load(f)
        description = config.get(source_name, {}).get("description", "")
    except Exception:
        description = ""

    schema = df.dtypes.astype(str).to_dict()
    sample = df.head(10).to_dict(orient="records")

    prompt = PROMPT_TEMPLATE.format(
        source_name=source_name,
        description=description,
        schema=json.dumps(schema, indent=2),
        sample=json.dumps(sample, indent=2, default=str),
        existing_rule_columns=json.dumps(existing_rule_columns),
    )

    print(f"[AI Rules] Inferring rules for '{source_name}'...")
    raw = _call_groq(prompt).strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    ai_rules = json.loads(raw)
    print(f"[AI Rules] Groq inferred {len(ai_rules)} rules")

    # Merge: business rules take priority, AI fills the gaps
    merged = business_rules + ai_rules
    print(f"[AI Rules] Total merged rules: {len(merged)}")

    return merged


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "include/src")
    from dotenv import load_dotenv
    load_dotenv()
    from extract import extract

    # Customers
    df_customers = extract("include/data/raw/customers.csv")
    rules_customers = infer_rules(df_customers, source_name="customers")
    with open("include/data/rules_customers.json", "w") as f:
        json.dump(rules_customers, f, indent=2)
    print(f"Customers: {len(rules_customers)} rules saved")

    # Transactions — merge with existing if present
    df_transactions = extract("include/data/raw/transactions.csv")
    rules_transactions = infer_rules(df_transactions, source_name="transactions")

    # Check if manual rules already exist
    existing_path = "include/data/rules_transactions.json"
    try:
        with open(existing_path) as f:
            existing = json.load(f)
        # Keep manual rules, add AI rules that don't overlap
        existing_cols_rules = {
            (r["column"], r["rule_type"]) for r in existing
        }
        new_rules = [
            r for r in rules_transactions
            if (r["column"], r["rule_type"]) not in existing_cols_rules
        ]
        final_rules = existing + new_rules
        print(f"Merged: {len(existing)} existing + {len(new_rules)} new = {len(final_rules)} total")
    except FileNotFoundError:
        final_rules = rules_transactions

    with open(existing_path, "w") as f:
        json.dump(final_rules, f, indent=2)
    print(f"Transactions: {len(final_rules)} rules saved")