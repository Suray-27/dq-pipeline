import json
import os
import hashlib
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


def get_schema_hash(df: pd.DataFrame) -> str:
    """Generate a hash of the schema — columns + dtypes."""
    schema = df.dtypes.astype(str).to_dict()
    schema_str = json.dumps(schema, sort_keys=True)
    return hashlib.md5(schema_str.encode()).hexdigest()


def get_cached_hash(source_name: str) -> str:
    """Load previously saved schema hash."""
    hash_path = f"include/data/.schema_hash_{source_name}.txt"
    try:
        with open(hash_path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def save_schema_hash(source_name: str, schema_hash: str):
    """Save current schema hash for next run comparison."""
    hash_path = f"include/data/.schema_hash_{source_name}.txt"
    with open(hash_path, "w") as f:
        f.write(schema_hash)
    print(f"[AI Rules] Schema hash saved for '{source_name}'")


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


def load_cached_rules(source_name: str) -> list:
    """Load previously saved rules from JSON file."""
    rules_path = f"include/data/rules_{source_name}.json"
    try:
        with open(rules_path) as f:
            rules = json.load(f)
        print(f"[AI Rules] Loaded {len(rules)} cached rules for '{source_name}'")
        return rules
    except FileNotFoundError:
        return []


def infer_rules(df: pd.DataFrame, source_name: str = "unknown") -> list:
    """
    Infer rules using Groq + merge with business config rules.
    Skips Groq call if schema hasn't changed since last run.
    """
    current_hash = get_schema_hash(df)
    cached_hash = get_cached_hash(source_name)

    # Check if schema changed
    if current_hash == cached_hash:
        cached_rules = load_cached_rules(source_name)
        if cached_rules:
            print(f"[AI Rules] Schema unchanged for '{source_name}' — skipping Groq, using cached rules")
            return cached_rules

    print(f"[AI Rules] Schema changed or first run for '{source_name}' — calling Groq...")

    # Load business rules
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

    raw = _call_groq(prompt).strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    ai_rules = json.loads(raw)
    print(f"[AI Rules] Groq inferred {len(ai_rules)} rules")

    # Merge business rules + AI rules
    existing_cols_rules = {(r["column"], r["rule_type"]) for r in business_rules}
    new_rules = [r for r in ai_rules if (r["column"], r["rule_type"]) not in existing_cols_rules]
    merged = business_rules + new_rules
    print(f"[AI Rules] Total merged rules: {len(merged)}")

    # Save rules and schema hash for next run
    rules_path = f"include/data/rules_{source_name}.json"
    with open(rules_path, "w") as f:
        json.dump(merged, f, indent=2)
    save_schema_hash(source_name, current_hash)

    return merged