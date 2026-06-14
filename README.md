# AI-Powered Data Quality Pipeline

An end-to-end data quality pipeline that uses LLMs to automatically infer data quality rules, validate data, and suggest fixes for violations.

## Architecture
Raw Source (CSV)

↓

Extract (Python + Pandas)

↓

AI Agent: Infers data quality rules from schema + sample data

(Groq LLM — llama-3.3-70b-versatile)

↓

Transform — standard cleaning (trim, normalize casing)

↓

Validate — run AI-generated rules as actual checks

↓

├── Pass → Load to curated table (Neon PostgreSQL)

└── Fail → AI Agent analyzes failures, suggests fixes

→ Load to quarantine table

↓

Orchestration: Airflow DAG on Astronomer (runs daily at 6am)

↓

Output: Streamlit Data Quality Dashboard

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| AI / LLM | Groq API (llama-3.3-70b-versatile) |
| Data Processing | Pandas |
| Database | Neon PostgreSQL (cloud) |
| Orchestration | Apache Airflow on Astronomer |
| Dashboard | Streamlit + Plotly |
| Containerization | Docker + Docker Compose |
| Version Control | Git + GitHub |

## Project Structure

dq_pipeline/

├── dags/

│   └── dq_pipeline_dag.py      # Airflow DAG

├── include/

│   ├── src/

│   │   ├── extract.py          # Extract raw data

│   │   ├── ai_rules.py         # AI rule inference (Groq)

│   │   ├── transform.py        # Standard cleaning

│   │   ├── validate.py         # Rule engine

│   │   ├── ai_fixes.py         # AI fix suggestions (Groq)

│   │   └── load.py             # Load to PostgreSQL

│   └── data/

│       └── raw/customers.csv   # Sample raw data

├── dashboard.py                # Streamlit dashboard

├── docker-compose.yml          # Local Docker setup

├── Dockerfile                  # Astronomer runtime

├── requirements.txt            # Python dependencies

└── .env                        # API keys (not committed)

## Data Quality Rules (AI-Inferred)

The AI agent automatically infers these rule types from schema and sample data:

| Rule Type | Description | Example |
|---|---|---|
| `not_null` | Column must have a value | `age` must not be null |
| `unique` | No duplicate values | `id` must be unique |
| `in_range` | Value within bounds | `age` between 0 and 120 |
| `valid_date` | Parseable date format | `signup_dt` in YYYY-MM-DD |
| `max_date` | Date not in future | `signup_dt` ≤ today |
| `regex` | Matches pattern | `email` matches email pattern |
| `allowed_values` | Value in allowed set | `status` in [active, inactive, pending] |

## Sample Results

Given 9 raw customer records with planted issues:

| Outcome | Rows |
|---|---|
| ✅ Curated (clean) | 3 |
| 🚫 Quarantined (violations) | 6 |
| ⚠️ Violations detected | 6 |

Issues caught:
- Duplicate `id`
- Invalid email format
- Unparseable date
- Null age
- Out-of-range age (150)
- Inconsistent status casing (auto-fixed in Transform)

## Setup & Running Locally

### Prerequisites
- Docker Desktop with WSL2
- Python 3.11+
- Groq API key ([console.groq.com](https://console.groq.com))

### Steps

```bash
# Clone the repo
git clone https://github.com/Suray-27/dq-pipeline.git
cd dq-pipeline

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your API keys

# Start PostgreSQL
docker-compose up -d

# Run the pipeline
python3 include/src/pipeline.py

# Launch dashboard
streamlit run dashboard.py
```

## Environment Variables

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Groq API key for LLM inference |
| `DB_URL` | PostgreSQL connection string |

## Dashboard

The Streamlit dashboard shows:
- Pipeline summary metrics (pass rate, violation count)
- Pass vs fail pie chart
- Violations breakdown by column and rule type
- Curated and quarantined data tables
- AI-generated fix suggestions per violated record

## Key Design Decisions

- **AI rules are structured JSON** — not free text, so they can be executed programmatically
- **Transform before Validate** — deterministic cleaning runs first to avoid false violations
- **Quarantine not delete** — bad rows are held for review, never discarded
- **AI fixes are suggestions only** — confidence scores guide human review, not auto-correction
- **XCom for task communication** — Airflow tasks pass data via XCom since each runs in a separate process

## Author

Surendhar 