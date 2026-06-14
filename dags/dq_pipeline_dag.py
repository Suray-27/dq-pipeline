import sys
import os
import json
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    "owner": "xander",
    "retries": 1,
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

    def extract_task(**context):
        sys.path.insert(0, "/usr/local/airflow/include/src")
        from extract import extract
        df = extract("/usr/local/airflow/include/data/raw/customers.csv")
        # Push to XCom as JSON string
        context["ti"].xcom_push(key="extracted", value=df.to_json())

    def infer_rules_task(**context):
        sys.path.insert(0, "/usr/local/airflow/include/src")
        import pandas as pd
        from ai_rules import infer_rules
        # Pull from XCom
        data = context["ti"].xcom_pull(task_ids="extract", key="extracted")
        df = pd.read_json(data)
        rules = infer_rules(df)
        context["ti"].xcom_push(key="rules", value=json.dumps(rules))

    def transform_task(**context):
        sys.path.insert(0, "/usr/local/airflow/include/src")
        import pandas as pd
        from transform import transform
        data = context["ti"].xcom_pull(task_ids="extract", key="extracted")
        df = pd.read_json(data)
        df = transform(df)
        context["ti"].xcom_push(key="transformed", value=df.to_json())

    def validate_task(**context):
        sys.path.insert(0, "/usr/local/airflow/include/src")
        import pandas as pd
        from validate import validate
        data = context["ti"].xcom_pull(task_ids="transform", key="transformed")
        rules_str = context["ti"].xcom_pull(task_ids="infer_rules", key="rules")
        df = pd.read_json(data)
        rules = json.loads(rules_str)
        passed, failed, violations = validate(df, rules)
        context["ti"].xcom_push(key="passed", value=passed.to_json())
        context["ti"].xcom_push(key="failed", value=failed.to_json())
        context["ti"].xcom_push(key="violations", value=json.dumps(violations, default=str))

    def ai_fixes_task(**context):
        sys.path.insert(0, "/usr/local/airflow/include/src")
        from ai_fixes import analyze_failures
        violations_str = context["ti"].xcom_pull(task_ids="validate", key="violations")
        violations = json.loads(violations_str)
        fixes = analyze_failures(violations) if violations else []
        context["ti"].xcom_push(key="fixes", value=json.dumps(fixes))

    def load_task(**context):
        sys.path.insert(0, "/usr/local/airflow/include/src")
        import pandas as pd
        from load import load
        passed = pd.read_json(context["ti"].xcom_pull(task_ids="validate", key="passed"))
        failed = pd.read_json(context["ti"].xcom_pull(task_ids="validate", key="failed"))
        violations = json.loads(context["ti"].xcom_pull(task_ids="validate", key="violations"))
        fixes = json.loads(context["ti"].xcom_pull(task_ids="ai_fixes", key="fixes"))
        load(passed, failed, violations, fixes)

    t1 = PythonOperator(task_id="extract", python_callable=extract_task)
    t2 = PythonOperator(task_id="infer_rules", python_callable=infer_rules_task)
    t3 = PythonOperator(task_id="transform", python_callable=transform_task)
    t4 = PythonOperator(task_id="validate", python_callable=validate_task)
    t5 = PythonOperator(task_id="ai_fixes", python_callable=ai_fixes_task)
    t6 = PythonOperator(task_id="load", python_callable=load_task)

    t1 >> t2 >> t3 >> t4 >> t5 >> t6