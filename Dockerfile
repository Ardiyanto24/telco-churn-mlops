# Milestone 3.1 — containerization inference service package (churn_prediction).
# python:3.13-slim dipilih forced-by-precedent: test.yml/batch-scoring.yml pin
# python-version "3.13" dan terbukti sukses memuat lightgbm==4.7.0/xgboost==3.4.0
# di linux sejak Milestone 2.7 -- lihat milestones/3.1-.../decisions.md Keputusan #1.
FROM python:3.13-slim

# libgomp1 -- KD-1 (docs/keterbatasan-diterima.md): wheel PyPI lightgbm tidak
# membundel libgomp.so.1. ubuntu-latest (GitHub Actions VM penuh) kebetulan
# punya lib ini; base image slim TIDAK menjamin sama -- diinstal eksplisit,
# bukan diasumsikan. Lihat decisions.md Keputusan #2.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Model TIDAK dibake ke image -- artifacs/ sengaja tidak di-COPY (lihat
# .dockerignore + decisions.md Keputusan #3). Model dimuat runtime dari
# MLflow registry (alias "champion") via env var saat `docker run`, supaya
# rollback model tetap cukup ganti alias registry, bukan rebuild+redeploy
# container (prinsip Bagian 5.2 dokumen arsitektur).
COPY pyproject.toml .
COPY src/ src/
COPY scripts/ scripts/

# Dependency inti churn_prediction saja (bukan .[dev]/.[orchestration]) --
# image ini untuk inference runtime, bukan test suite/flow Prefect. Lihat
# decisions.md Keputusan #4.
RUN pip install --no-cache-dir .

# Milestone 3.2 -- real-time inference API. fastapi/uvicorn sudah ikut
# ter-install lewat dependency inti di atas (pyproject.toml). Model TETAP
# dimuat runtime dari MLflow registry (lihat app.py lifespan), bukan dibake
# ke image -- prinsip rollback-via-alias (M3.1 decisions.md Keputusan #3)
# masih berlaku persis sama di sini.
EXPOSE 8000
CMD ["uvicorn", "churn_prediction.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
