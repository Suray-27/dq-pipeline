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
    schema = df.dtypes.astype(str).to_dict()
    schema_str = json.dumps(schema, sort_keys=True)
    return hashlib.md5(schema_str.encode()).hexdigest()


def get_cached_hash(source_name: str) -> str:
    from config import get_metadata
    val = get_metadata(str(source_name).lower().strip(), "schema_hash")
    return str(val).strip() if val else None


def save_schema_hash(source_name: str, schema_hash: str,
                     pipeline_run_id: str = "", source_run_id: str = ""):
    from config import set_metadata
    set_metadata(str(source_name).lower().strip(), "schema_hash", schema_hash,
                 pipeline_run_id, source_run_id)


def save_rules(source_name: str, rules: list,
               pipeline_run_id: str = "", source_run_id: str = ""):
    from config import set_metadata
    set_metadata(str(source_name).lower().strip(), "rules", json.dumps(rules),
                 pipeline_run_id, source_run_id)


def load_business_rules(source_name: str) -> list:
    """Loads human-defined business validation rules from the local config JSON file."""
    BUSINESS_RULES_FILE = os.environ.get("BUSINESS_RULES_FILE_PATH", "data/business_rules.json")
    
    try:
        if os.path.exists(BUSINESS_RULES_FILE):
            with open(BUSINESS_RULES_FILE) as f:
                config = json.load(f)
            
            rules = config.get(source_name, {}).get("rules", [])
            if rules:
                print(f"[AI Rules] Loaded {len(rules)} local business rules for '{source_name}'")
                return rules
    except Exception as e:
        print(f"[AI Rules] Warning: Could not read business rules file: {e}")
        
    print(f"[AI Rules] No business rules found in JSON config for '{source_name}'")
    return []


def load_cached_rules(source_name: str) -> list:
    from config import get_metadata
    rules_json = get_metadata(str(source_name).lower().strip(), "rules")
    if rules_json:
        rules = json.loads(rules_json)
        print(f"[AI Rules] Loaded {len(rules)} cached rules from Snowflake for '{source_name}'")
        return rules
    return []


def infer_rules(df: pd.DataFrame, source_name: str = "unknown",
                pipeline_run_id: str = "", source_run_id: str = "") -> list:
    current_hash = get_schema_hash(df)
    cached_hash = get_cached_hash(source_name)

    if cached_hash and current_hash == cached_hash:
        cached_rules = load_cached_rules(source_name)
        if cached_rules:
            print(f"[AI Rules] Schema unchanged for '{source_name}' — skipping Groq, using cached rules")
            return cached_rules

    print(f"[AI Rules] Schema changed for '{source_name}' — calling Groq...")

    # 🛠️ FIX #1: Define the file path variable first
    BUSINESS_RULES_FILE = os.environ.get("BUSINESS_RULES_FILE_PATH", "data/business_rules.json")

    # 🛠️ FIX #2: Extract the table description immediately while opening the file
    try:
        with open(BUSINESS_RULES_FILE) as f:
            config = json.load(f)
        description = config.get(source_name, {}).get("description", "")
    except Exception:
        description = ""

    # 🛠️ FIX #3: Pass the file path into your rule loader if it reads locally
    business_rules = load_business_rules(source_name) 
    existing_rule_columns = list({r["column"] for r in business_rules})

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
        lines = raw.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    ai_rules = json.loads(raw)
    print(f"[AI Rules] Groq inferred {len(ai_rules)} rules")

    existing_cols_rules = {(r["column"], r["rule_type"]) for r in business_rules}
    new_rules = [r for r in ai_rules
                 if (r["column"], r["rule_type"]) not in existing_cols_rules]
    merged = business_rules + new_rules
    print(f"[AI Rules] Total merged rules: {len(merged)}")

    save_rules(source_name, merged, pipeline_run_id, source_run_id)
    save_schema_hash(source_name, current_hash, pipeline_run_id, source_run_id)

    return merged