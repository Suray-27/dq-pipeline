import json
import os
import requests


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


PROMPT_TEMPLATE = """You are a data quality analyst.
Below are data quality violations found in a customer dataset.
For each violation suggest a specific fix.

Respond as a JSON array, one object per violation, each with:
- "row_index": same as input
- "id": same as input
- "column": same as input
- "issue": short restatement of the problem
- "suggested_fix": concrete proposed value or action
- "confidence": one of ["high", "medium", "low"]

Violations:
{violations}

Respond with ONLY the JSON array, no other text, no markdown fences.
"""


def analyze_failures(violations: list) -> list:
    prompt = PROMPT_TEMPLATE.format(
        violations=json.dumps(violations, indent=2, default=str)
    )

    print("[AI Fixes] Sending violations to Groq...")
    raw = _call_groq(prompt).strip()

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    fixes = json.loads(raw)
    print(f"[AI Fixes] Received {len(fixes)} suggestions")
    return fixes


if __name__ == "__main__":
    with open("data/violations.json") as f:
        violations = json.load(f)

    fixes = analyze_failures(violations)

    print("\n--- AI Fix Suggestions ---")
    for fix in fixes:
        print(f"\n  Row {fix['row_index']} | {fix['column']}")
        print(f"  Issue      : {fix['issue']}")
        print(f"  Fix        : {fix['suggested_fix']}")
        print(f"  Confidence : {fix['confidence']}")

    with open("data/fix_suggestions.json", "w") as f:
        json.dump(fixes, f, indent=2)
    print("\n[AI Fixes] Saved to data/fix_suggestions.json")