# AI-Powered Data Quality & Ingestion Pipeline

[![CI](https://github.com/Suray-27/dq-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Suray-27/dq-pipeline/actions/workflows/ci.yml)

An automated, metadata-driven **Extract-Transform-Load (ELT)** data quality orchestration pipeline. The system processes incoming datasets, automatically intercepts structural schema drift, generates adaptive validation rules using Large Language Models, quarantines compliance violations, and provides natural language root-cause diagnostic feedback.

---

## 🏗️ Conceptual Architecture & Data Flow

The project is built around the principle of **Closed-Loop Data Quality Management**. Instead of allowing anomalous data to break production models or downstream dashboards, the pipeline separates data content validation from structural schema mutations using a modular architecture.

```
[ Raw CSV Input File Layer ]
│
▼

EXTRACT ─────────► [ MD5 Signature Match? ] ──(Yes)──► Skip Execution
│ (No)
▼

DRIFT INSPECTOR ◄► [ Snowflake Schema Registry ] ──(Changed/First Run)──► Groq AI Impact Analysis
│ (Unchanged)
▼

RULES ENGINE ◄───► [ Local JSON Cache State ] ───────(Missing Columns)──► Groq AI Adaptive Inference
│
▼

VALIDATION ENGINE ──► [ Vectorized Check Array ]
├── (Passed Rows) ──────► 5. LOAD ──► [ Curated Snowflake Tables ]
└── (Quarantined Rows) ──► 6. DIAGNOSTIC LAYER ──► Groq AI Root-Cause ──► [ Violations & Fixes Logs ]
```

### 🧠 The Core Data Lifecycle Engineering Concepts

#### 1. Optimization-First Ingestion Gate
To protect database computation metrics and avoid redundant processing, raw data is first cryptographically fingerprinted using an MD5 hash check. If the signature matches a previously completed entry in Snowflake's log layer, the run completes instantly without consuming compute or API quotas.

#### 2. Isolated Schema Drift Tracking
Data layout alterations (added columns, dropped columns, or mutated data types) represent structural modifications rather than day-to-day transaction records. The pipeline decouples this check into a separate schema tracking layer. Groq's LLM is brought in only when layout mutations appear, creating clear documentation of the changes without slowing down normal ingestion.

#### 3. Hybrid Automated Rules Engines
Hardcoded rules quickly fall behind real-world data tracking needs. The engine uses a hybrid system that merges static user constraints (like `business_rules.json`) with dynamic, AI-inferred column boundaries drawn from statistical data samples.

#### 4. Vectorized Filtering Matrices
Instead of handling records using slow Python iteration structures, datasets are run through parallel vectorized Pandas conditional logic arrays. High-quality items flow straight to the `curated` analysis targets, while failing rows are isolated, evaluated for errors, and routed directly to a `quarantine` space.

#### 5. Conversational Analytics Layer
The application leverages a persistent session loop to create a contextual chat data experience. When you query data anomalies in plain language via the Streamlit dashboard, the system binds live error violation metrics to the foundational context window, allowing you to debug data health issues without writing complex SQL code.

---

## 🛠️ Tech Stack Matrix

| Architectural Layer | Technology Deployment |
|---|---|
| Language Runtime | Python 3.12 |
| AI / LLM Engine | Groq API (`llama-3.3-70b-versatile`) |
| Core Processing Engine | Pandas DataFrames |
| Cloud Storage / Target Warehouse | Snowflake (Case-safe unquoted identifiers) |
| Orchestration Framework | Apache Airflow on Astronomer Platform / Local Wrapper Engine |
| Metrics UI Dashboard | Streamlit Dashboard Layer |
| Containerized Runtime Environment | Docker + Docker Compose Multi-Container Toolset |
| Source Control / Versioning | Git + GitHub Actions |

---

## ⚙️ Data Quality Rules Engine Options

The vectorized processing engine natively translates these validation strategies inside the pipeline:

| Rule Strategy Tag | Functional Description | Expected Parameter Structure (`params`) |
|---|---|---|
| `not_null` | Blocks missing values, spaces, or unparsed `nan` types. | `{}` |
| `unique` | Blocks duplicate records inside targeted unique fields. | `{}` |
| `in_range` | Restricts numerical entry systems to upper and lower bounds. | `{"min": 1, "max": 5000}` |
| `valid_date` | Confirms calendar data parameters match layout settings. | `{"format": "%Y-%m-%d"}` |
| `max_date` | Catches anomalous forward dates set in the future. | `{"format": "%Y-%m-%d", "max": "today"}` |
| `regex` | Validates value layouts using strict text pattern matching. | `{"pattern": "^[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}$"}` |
| `allowed_values` | Restricts properties to an exact set of categorical strings. | `{"values": ["success", "failed", "pending"]}` |

---

## Project Structure

```

```

## 🚀 Setup & Execution Quickstart

### Prerequisites
* Docker Desktop with active WSL2 integration
- Python 3.12+ environment
- Groq API credentials profile account
- Connected Snowflake database instance setup workspace

### Ingestion Execution Command Sequences

```bash
# Initialize isolated Python virtual environment workspace
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure system environment configurations
cp .env.example .env
# Edit .env parameters to assign your Snowflake user credentials and Groq API token

# Initialize standard execution tracking log structures in Snowflake
python3 include/src/config.py

# Run the ingestion orchestrator engine locally
python3 include/src/pipeline.py

# Boot up the interactive operational visualization metrics cockpit
streamlit run dashboard.py

## Author

Surendhar 