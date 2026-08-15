# Milestone 3.9 -- image LEAN untuk metrics_aggregator, TERPISAH dari 2
# exporter existing (pipeline-health-exporter/drift-exporter) dan
# churn-inference. Komponen ini MEMBACA dari Prometheus sbg client HTTP
# (requests) lalu menulis ke PostgreSQL (sqlalchemy+psycopg2-binary) --
# TIDAK expose /metrics sendiri (TIDAK butuh prometheus_client), TIDAK
# butuh pandas/scipy/numpy/lightgbm/xgboost/mlflow (tidak pernah
# transform/load model). Diharapkan jadi image PALING LEAN di antara 3
# komponen monitoring (drift-exporter 621MB, pipeline-health-exporter
# 534MB). Lihat
# milestones/3.9-penyimpanan-data-monitoring-postgresql/decisions.md.
#
# Build dari ROOT REPO (context perlu orchestration/monitoring/):
#   docker build -f infra/docker/metrics-aggregator.Dockerfile -t metrics-aggregator:m3.9 .
FROM python:3.13-slim

WORKDIR /app

# Versi dipin persis sama dengan yang resolve di pyproject.toml.
RUN pip install --no-cache-dir \
    requests==2.34.2 \
    sqlalchemy==2.0.52 \
    psycopg2-binary==2.9.12

COPY orchestration/monitoring/metrics_aggregator.py orchestration/monitoring/metrics_aggregator.py

CMD ["python", "-u", "orchestration/monitoring/metrics_aggregator.py"]
