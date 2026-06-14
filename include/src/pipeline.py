import json
import os
import sys
sys.path.insert(0, "include/src")

from extract import extract
from transform import transform
from validate import validate
from ai_rules import infer_rules
from ai_fixes import analyze_failures
from load import load


def run():
    print("\n========== DQ PIPELINE STARTED ==========\n")

    # Step 1: Extract
    df = extract("data/raw/customers.csv")

    # Step 2: Infer rules using Groq
    rules = infer_rules(df)
    with open("data/rules.json", "w") as f:
        json.dump(rules, f, indent=2)

    # Step 3: Transform
    df = transform(df)

    # Step 4: Validate
    passed, failed, violations = validate(df, rules)
    with open("data/violations.json", "w") as f:
        json.dump(violations, f, indent=2, default=str)

    # Step 5: AI Fix Suggestions
    fixes = analyze_failures(violations) if violations else []
    with open("data/fix_suggestions.json", "w") as f:
        json.dump(fixes, f, indent=2)

    # Step 6: Load to PostgreSQL
    load(passed, failed, violations, fixes)

    print("\n========== DQ PIPELINE COMPLETED ==========\n")


if __name__ == "__main__":
    run()