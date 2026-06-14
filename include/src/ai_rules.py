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

Schema:
{schema}

Sample rows (JSON):
{sample}

Respond with ONLY the JSON array, no other text, no markdown fences.
"""


def infer_rules(df: pd.DataFrame) -> list:
    schema = df.dtypes.astype(str).to_dict()
    sample = df.head(10).to_dict(orient="records")

    prompt = PROMPT_TEMPLATE.format(
        schema=json.dumps(schema, indent=2),
        sample=json.dumps(sample, indent=2, default=str),
    )

    print("[AI Rules] Sending schema + sample to Groq...")
    raw = _call_groq(prompt).strip()

    # strip markdown fences if model adds them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    rules = json.loads(raw)
    print(f"[AI Rules] Received {len(rules)} rules")
    return rules


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "include/src")
    from extract import extract

    df = extract("data/raw/customers.csv")
    rules = infer_rules(df)

    print("\n--- Rules Inferred ---")
    for r in rules:
        print(f"\n  Column : {r['column']}")
        print(f"  Rule   : {r['rule_type']} {r['params']}")
        print(f"  Reason : {r['reasoning']}")

    os.makedirs("data", exist_ok=True)
    with open("data/rules.json", "w") as f:
        json.dump(rules, f, indent=2)
    print("\n[AI Rules] Saved to data/rules.json")