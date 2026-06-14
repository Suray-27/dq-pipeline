FROM quay.io/astronomer/astro-runtime:3.2-5

# Switch to root to install packages
USER root

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY src/ /usr/local/airflow/src/
COPY data/ /usr/local/airflow/data/

# Switch back to airflow user
USER astro