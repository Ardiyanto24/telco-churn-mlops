# Milestone 3.6 -- image LEAN untuk drift_exporter, TERPISAH dari
# pipeline-health-exporter (M3.5) dan churn-inference. Exporter cuma baca
# tabel HASIL JADI (drift.drift_check_results) -- TIDAK butuh scipy/
# transform/mlflow (komputasi PSI/KS/Chi2 terjadi di scripts/compute_drift.py
# lewat GitHub Actions, bukan di sini). Lihat
# milestones/3.6-monitoring-drift-kualitas-model/decisions.md Keputusan #1.
#
# Butuh churn_prediction.drift.metrics (fungsi verdict_to_value(), pure/tanpa
# dependency berat) -- install package inti TANPA lightgbm/xgboost/mlflow
# butuh workaround: install dependency inti manual (scipy TIDAK termasuk,
# drift.metrics import scipy di level modul -- lihat catatan di bawah).
#
# Build dari ROOT REPO:
#   docker build -f infra/docker/drift-exporter.Dockerfile -t drift-exporter:m3.6 .
FROM python:3.13-slim

WORKDIR /app

# prometheus_client+sqlalchemy+psycopg2-binary -- pola sama exporter.Dockerfile
# (M3.5). scipy ditambah karena churn_prediction.drift.metrics (dipakai untuk
# verdict_to_value()) import scipy.stats di level modul -- masih SANGAT
# ringan dibanding lightgbm/xgboost/mlflow-skinny yang TIDAK dibutuhkan sama
# sekali (exporter tidak pernah transform/load model).
RUN pip install --no-cache-dir \
    prometheus_client==0.26.0 \
    sqlalchemy==2.0.52 \
    psycopg2-binary==2.9.12 \
    scipy==1.17.1 \
    numpy==2.5.2 \
    pandas==3.0.5

COPY src/churn_prediction/drift/ src/churn_prediction/drift/
COPY src/churn_prediction/__init__.py src/churn_prediction/__init__.py
COPY orchestration/monitoring/drift_exporter.py orchestration/monitoring/drift_exporter.py

ENV PYTHONPATH=/app/src

EXPOSE 9101
CMD ["python", "-u", "orchestration/monitoring/drift_exporter.py"]
