# Milestone 3.5 -- image LEAN untuk pipeline_health_exporter, TERPISAH dari
# image churn-inference (Dockerfile root). Exporter tidak pernah memuat model
# (tidak import churn_prediction.inference sama sekali) -- deps-nya cuma 4
# package di bawah, TANPA lightgbm/xgboost/mlflow-skinny/scikit-learn yang
# mendominasi ukuran image churn-inference (~1.63GB, GPU dep tidak terpakai,
# M3.1). Lihat milestones/3.5-monitoring-infra-pipeline-health/decisions.md
# Keputusan #3.
#
# Build dari ROOT REPO (context perlu orchestration/monitoring/):
#   docker build -f infra/docker/exporter.Dockerfile -t pipeline-health-exporter:m3.5 .
FROM python:3.13-slim

WORKDIR /app

# Versi dipin persis sama dengan yang resolve di pyproject.toml (core deps +
# extra "orchestration") -- satu sumber kebenaran versi, bukan floating.
RUN pip install --no-cache-dir \
    prometheus_client==0.26.0 \
    prefect==3.8.2 \
    sqlalchemy==2.0.52 \
    psycopg2-binary==2.9.12

COPY orchestration/monitoring/pipeline_health_exporter.py orchestration/monitoring/pipeline_health_exporter.py

EXPOSE 9100
CMD ["python", "-u", "orchestration/monitoring/pipeline_health_exporter.py"]
