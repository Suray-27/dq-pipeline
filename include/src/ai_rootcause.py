import os
import json
import requests
import sys
sys.path.insert(0, "include/src")
from dotenv import load_dotenv
load_dotenv()

from config import SOURCES
from extract import extract
from transform import transform
from validate import validate
from ai_rules import infer_rules
import json


def _call_reasoning_model(prompt: str) -> str:
    """Call Qwen3 reasoning model via Groq API."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {
        "model": "qwen/qwen3-32b",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=body,
    )
    print(f"[Root Cause] Status code: {response.status_code}")
    print(f"[Root Cause] Raw response: {response.text[:500]}")
    response.raise_for_status()
    
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    print(f"[Root Cause] Content received: {content[:200] if content else 'EMPTY'}")
    return content


PROMPT_TEMPLATE = """You are a senior data engineer performing cross-table 
root cause analysis on data quality violations.

Analyze ALL violations across ALL tables together and identify:
1. Root causes — what systemic issues caused these violations
2. Cross-table connections — how violations in one table caused violations in another
3. Priority fixes — which single fix would resolve the most violations
4. Systemic recommendations — what process/system changes prevent recurrence

Think step by step. Look for patterns across tables, not just individual records.

Tables processed:
{tables_summary}

All violations across all tables:
{all_violations}

Cross-table dependencies:
{dependencies}

Respond in this exact JSON format:
{{
  "root_causes": [
    {{
      "cause": "description of root cause",
      "affected_tables": ["table1", "table2"],
      "affected_columns": ["col1", "col2"],
      "violation_count": 3,
      "severity": "high/medium/low"
    }}
  ],
  "cross_table_impacts": [
    {{
      "source_table": "customers",
      "source_issue": "duplicate id=1",
      "downstream_table": "transactions",
      "downstream_impact": "3 referential integrity failures",
      "cascade_count": 3
    }}
  ],
  "priority_fixes": [
    {{
      "fix": "description of fix",
      "resolves_violations": 4,
      "effort": "low/medium/high"
    }}
  ],
  "systemic_recommendations": [
    "recommendation 1",
    "recommendation 2"
  ],
  "overall_health": "poor/fair/good/excellent",
  "executive_summary": "2-3 sentence plain English summary for business stakeholders"
}}

Respond with ONLY the JSON, no markdown fences, no think tags.
"""


def analyze_root_causes(
    tables_results: dict,
    dependencies: dict = None,
) -> dict:
    """
    Perform cross-table root cause analysis.
    
    tables_results: {
        "customers": {"violations": [...], "passed": df, "failed": df},
        "transactions": {"violations": [...], "passed": df, "failed": df},
    }
    dependencies: {
        "transactions": ["curated_customers"]
    }
    """

    # Build tables summary
    tables_summary = {}
    all_violations = []

    for table, result in tables_results.items():
        violations = result.get("violations", [])
        tables_summary[table] = {
            "total_records": result.get("total_records", 0),
            "passed": result.get("passed_count", 0),
            "failed": result.get("failed_count", 0),
            "violation_count": len(violations),
            "violated_columns": list({v["column_name"] for v in violations}),
        }
        # Tag each violation with its source table
        for v in violations:
            v["source_table"] = table
            all_violations.append(v)

    if not all_violations:
        return {
            "root_causes": [],
            "cross_table_impacts": [],
            "priority_fixes": [],
            "systemic_recommendations": ["No violations found — data quality is excellent"],
            "overall_health": "excellent",
            "executive_summary": "All records passed quality checks across all tables.",
        }

    prompt = PROMPT_TEMPLATE.format(
        tables_summary=json.dumps(tables_summary, indent=2),
        all_violations=json.dumps(all_violations, indent=2, default=str),
        dependencies=json.dumps(dependencies or {}, indent=2),
    )

    print("[Root Cause] reasoning model...")
    raw = _call_reasoning_model(prompt).strip()

    # Strip think tags if model includes them
    if "<think>" in raw:
        raw = raw.split("</think>")[-1].strip()

    # Strip markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    result = json.loads(raw)
    print(f"[Root Cause] Found {len(result.get('root_causes', []))} root causes")
    return result


if __name__ == "__main__":

    tables_results = {}

    for source_name, source in SOURCES.items():
        df = extract(source["file"])
        rules = infer_rules(df, source_name=source_name)
        passed, failed, violations = validate(transform(df), rules)

        tables_results[source_name] = {
            "total_records": len(df),
            "passed_count": len(passed),
            "failed_count": len(failed),
            "violations": violations,
        }

    # Dependencies from config
    dependencies = {
        s: SOURCES[s]["depends_on"]
        for s in tables_results
        if SOURCES[s]["depends_on"]
    }

    result = analyze_root_causes(tables_results, dependencies)

    print(f"\nOverall Health  : {result['overall_health']}")
    print(f"Executive Summary: {result['executive_summary']}")
    print(f"\nRoot Causes ({len(result['root_causes'])}):")
    for rc in result["root_causes"]:
        print(f"  [{rc['severity'].upper()}] {rc['cause']}")
    print(f"\nPriority Fixes:")
    for fix in result["priority_fixes"]:
        print(f"  [{fix['effort']}] {fix['fix']} → {fix['resolves_violations']} violations")