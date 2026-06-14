import os
import json
import requests
from datetime import datetime


def _call_groq(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=body,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


PROMPT_TEMPLATE = """You are a data quality analyst writing a summary report
for business stakeholders who are not technical.

Given the pipeline run results below, write a clear, concise summary in plain English.
Include:
- How many records were processed
- How many passed and failed
- What specific issues were found and in which columns
- What the business impact might be
- A clear recommendation for next steps
- An overall data quality score as a percentage

Keep it professional but easy to understand. No technical jargon.
No mention of code, DataFrames, or rule types.

Pipeline Run Results:
- Run timestamp: {timestamp}
- Total records: {total}
- Curated (passed): {passed}
- Quarantined (failed): {failed}
- Pass rate: {pass_rate}%
- Violations found:
{violations_summary}

Fix suggestions:
{fixes_summary}
"""


def generate_summary(
    passed_count: int,
    failed_count: int,
    violations: list,
    fixes: list,
) -> dict:

    total = passed_count + failed_count
    pass_rate = round(passed_count / total * 100, 1) if total > 0 else 0
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build violations summary
    violations_summary = ""
    by_column = {}
    for v in violations:
        col = v["column"]
        if col not in by_column:
            by_column[col] = []
        by_column[col].append(v["message"])

    for col, messages in by_column.items():
        violations_summary += f"  - {col}: {len(messages)} issue(s) — {messages[0]}\n"

    # Build fixes summary
    fixes_summary = ""
    for f in fixes:
        fixes_summary += (
            f"  - Row {f['row_index']} ({f['column']}): "
            f"{f['suggested_fix']} "
            f"[confidence: {f.get('confidence', 'N/A')}]\n"
        )

    prompt = PROMPT_TEMPLATE.format(
        timestamp=timestamp,
        total=total,
        passed=passed_count,
        failed=failed_count,
        pass_rate=pass_rate,
        violations_summary=violations_summary,
        fixes_summary=fixes_summary,
    )

    print("[AI Summary] Generating run summary...")
    summary_text = _call_groq(prompt)

    return {
        "timestamp": timestamp,
        "total_records": total,
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate": pass_rate,
        "summary": summary_text,
    }


if __name__ == "__main__":
    # Test with mock data
    violations = [
        {"column": "id", "message": "id has duplicate value", "row_index": 0},
        {"column": "id", "message": "id has duplicate value", "row_index": 8},
        {"column": "email", "message": "email does not match pattern", "row_index": 4},
        {"column": "signup_dt", "message": "signup_dt is not a valid date", "row_index": 6},
        {"column": "age", "message": "age outside range [0, 120]", "row_index": 5},
        {"column": "age", "message": "age is null", "row_index": 3},
    ]
    fixes = [
        {"row_index": 0, "column": "id", "suggested_fix": "Regenerate unique id", "confidence": "high"},
        {"row_index": 4, "column": "email", "suggested_fix": "Request correct email", "confidence": "low"},
    ]

    result = generate_summary(3, 6, violations, fixes)
    print("\n--- AI Summary ---\n")
    print(result["summary"])