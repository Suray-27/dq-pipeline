import os
import json
import requests
from datetime import datetime
import sys

# Dynamic environment paths with fallback defaults
SRC_DIR = os.environ.get("SRC_DIR", "include/src")
sys.path.insert(0, SRC_DIR)

from dotenv import load_dotenv
load_dotenv()

from config import SOURCES
from extract import extract
from transform import transform
from validate import validate
from ai_rules import infer_rules


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
        col = v.get("column_name") or v.get("column", "unknown")  # handle both
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

    all_violations = []
    all_fixes = []
    total_passed = 0
    total_failed = 0

    for source_name, source in SOURCES.items():
        df = extract(source["file"])
        rules = infer_rules(df, source_name=source_name)
        passed, failed, violations = validate(transform(df), rules)

        all_violations += violations
        total_passed += len(passed)
        total_failed += len(failed)

    # Generate summary with real data
    summary = generate_summary(
        total_passed,
        total_failed,
        all_violations,
        all_fixes
    )

    print("\n--- AI Summary ---\n")
    print(f"Timestamp  : {summary['timestamp']}")
    print(f"Total      : {summary['total_records']}")
    print(f"Passed     : {summary['passed']}")
    print(f"Failed     : {summary['failed']}")
    print(f"Pass Rate  : {summary['pass_rate']}%")
    print(f"\nSummary:\n{summary['summary']}")