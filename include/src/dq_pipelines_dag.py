import os
import sys
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime, timedelta

AIRFLOW_SRC_DIR = os.environ.get("AIRFLOW_SRC_DIR", "/usr/local/airflow/include/src")
if AIRFLOW_SRC_DIR not in sys.path:
    sys.path.insert(0, AIRFLOW_SRC_DIR)

from config import SOURCES

default_args = {
    "owner": "xander",
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
    "email_on_failure": False,
}

with DAG(
    dag_id="dq_pipeline_v2",
    default_args=default_args,
    description="Enterprise Multi-Source AI Data Quality Pipeline",
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["data-quality", "ai", "multi-source"],
) as dag:

    def run_pipeline_for_source(source_name, **context):
        """Processes an individual source fully through the workflow engine step-by-step."""
        import json
        import pandas as pd
        from datetime import datetime
        
        from extract import extract
        from transform import transform
        from validate import validate
        from ai_rules import infer_rules
        from ai_drift import detect_drift
        from ai_fixes import analyze_failures
        from load import load
        
        source_info = SOURCES[source_name]
        run_id = datetime.now().strftime("%Y%m%d%H%M%S")
        
        print(f"Starting Multi-Source workflow execution loop for: {source_name}")
        
        # 1. Ingest & Drift Track
        df_raw = extract(source_info["file"])
        drift_report = detect_drift(df_raw, source_name=source_name, run_id=run_id)
        
        # 2. Rule Inference Engine
        rules = infer_rules(df_raw, source_name=source_name)
        
        # 3. Clean and Validate
        df_clean = transform(df_raw, source_name=source_name)
        passed, failed, violations = validate(df_clean, rules)
        
        # 4. AI Repair Layer
        fixes = analyze_failures(violations) if violations else []
        
        # 5. Database Commit Staging
        load(passed, failed, violations, fixes, source_name=source_name)
        
        # Package and bubble data out to pipeline-wide metrics aggregates
        return {
            "source_name": source_name,
            "passed_count": len(passed),
            "failed_count": len(failed),
            "violations": violations,
            "fixes": fixes,
            "drift": drift_report
        }

    def aggregate_global_analysis_task(**context):
        """Collects metrics from ALL processed sources to generate global summaries and root causes."""
        import json
        from ai_summary import generate_summary
        from ai_root_cause import analyze_root_causes
        
        global_results = {}
        all_violations = []
        all_fixes = []
        total_passed = 0
        total_failed = 0
        
        # Pull performance metrics dynamically out of every single executed upstream task loop
        for source_name in SOURCES.keys():
            task_data = context["ti"].xcom_pull(task_ids=f"process_{source_name}")
            if task_data:
                global_results[source_name] = task_data
                all_violations += task_data["violations"]
                all_fixes += task_data["fixes"]
                total_passed += task_data["passed_count"]
                total_failed += task_data["failed_count"]

        # Run multi-source metrics cross-evaluations
        summary = generate_summary(total_passed, total_failed, all_violations, all_fixes)
        
        dependencies = {s: SOURCES[s]["depends_on"] for s in SOURCES if SOURCES[s]["depends_on"]}
        root_cause = analyze_root_causes(global_results, dependencies=dependencies)
        
        print("[Global Aggregator] Complete Pipeline Cross-Table Assessment Finished.")

    # Dynamically build pipeline nodes inside the DAG for every file defined in your config matrix
    summary_task = PythonOperator(
        task_id="global_pipeline_summary",
        python_callable=aggregate_global_analysis_task,
        provide_context=True
    )

    for source in SOURCES.keys():
        process_task = PythonOperator(
            task_id=f"process_{source}",
            python_callable=run_pipeline_for_source,
            op_kwargs={"source_name": source},
            provide_context=True
        )
        # Each unique file pipeline processing loop runs before feeding into the collective cross-table AI analytics node
        process_task >> summary_task