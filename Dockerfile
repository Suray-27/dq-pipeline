FROM quay.io/astronomer/astro-runtime:3.2-5

USER root

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

USER astro