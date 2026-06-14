import sys
import os
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import json


default_args = {
    "owner": "xander",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "email_on_failure": False,
}

with DAG(
    dag_id="dq_pipeline",
    default_args=default_args,
    description="AI-powered Data Quality Pipeline",
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["data-quality", "ai"],
) as dag:

    def extract_task():
        import sys
        sys.path.insert(0, "/usr/local/airflow/include/src")
        from extract import extract
        df = extract("/usr/local/airflow/include/data/raw/customers.csv")
        df.to_csv("/tmp/extracted.csv", index=False)

    def infer_rules_task():
        import sys
        sys.path.insert(0, "/usr/local/airflow/include/src")
        import pandas as pd
        from ai_rules import infer_rules
        df = pd.read_csv("/tmp/extracted.csv")
        rules = infer_rules(df)
        with open("/tmp/rules.json", "w") as f:
            json.dump(rules, f)

    def transform_task():
        import sys
        sys.path.insert(0, "/usr/local/airflow/include/src")
        import pandas as pd
        from transform import transform
        df = pd.read_csv("/tmp/extracted.csv")
        df = transform(df)
        df.to_csv("/tmp/transformed.csv", index=False)

    def validate_task():
        import sys
        sys.path.insert(0, "/usr/local/airflow/include/src")
        import pandas as pd
        from validate import validate
        df = pd.read_csv("/tmp/transformed.csv")
        with open("/tmp/rules.json") as f:
            rules = json.load(f)
        passed, failed, violations = validate(df, rules)
        passed.to_csv("/tmp/passed.csv", index=False)
        failed.to_csv("/tmp/failed.csv", index=False)
        with open("/tmp/violations.json", "w") as f:
            json.dump(violations, f, default=str)

    def ai_fixes_task():
        import sys
        sys.path.insert(0, "/usr/local/airflow/include/src")
        from ai_fixes import analyze_failures
        with open("/tmp/violations.json") as f:
            violations = json.load(f)
        fixes = analyze_failures(violations) if violations else []
        with open("/tmp/fixes.json", "w") as f:
            json.dump(fixes, f)

    def load_task():
        import sys
        sys.path.insert(0, "/usr/local/airflow/include/src")
        import pandas as pd
        from load import load
        passed = pd.read_csv("/tmp/passed.csv")
        failed = pd.read_csv("/tmp/failed.csv")
        with open("/tmp/violations.json") as f:
            violations = json.load(f)
        with open("/tmp/fixes.json") as f:
            fixes = json.load(f)
        load(passed, failed, violations, fixes)

    t1 = PythonOperator(task_id="extract", python_callable=extract_task)
    t2 = PythonOperator(task_id="infer_rules", python_callable=infer_rules_task)
    t3 = PythonOperator(task_id="transform", python_callable=transform_task)
    t4 = PythonOperator(task_id="validate", python_callable=validate_task)
    t5 = PythonOperator(task_id="ai_fixes", python_callable=ai_fixes_task)
    t6 = PythonOperator(task_id="load", python_callable=load_task)

    t1 >> t2 >> t3 >> t4 >> t5 >> t6
