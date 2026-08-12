"""Konstanta modul ``inference`` -- Milestone 1.5.

Sumber:
- ``THRESHOLD``/``POSITIVE_CLASS_INDEX``: docs/03-notebook-audit/notebook-audit.md
  Bagian D (Kontrak Model) -- ``model.predict_proba(X)[:, 1]``, threshold produksi
  0.6238 (F1-optimal, recall floor 0.60).
- ``DEFAULT_TRACKING_URI``: milestones/1.5-inference-service/decisions.md
  Keputusan #1 dan #7 (lokal/sementara milik M1.5, backend SQLite -- backend
  filesystem murni ``file:./mlruns`` berstatus maintenance mode di mlflow 3.15.1).
"""

import os

# Threshold klasifikasi produksi (notebook-audit.md Bagian D) -- disimpan di
# dalam bundle pyfunc per versi (bukan konstanta global dipakai ulang di
# predictor.py), lihat decisions.md Keputusan #3.
THRESHOLD = 0.6238
POSITIVE_CLASS_INDEX = 1

MODEL_NAME = "churn_prediction_model"

# Alias MLflow Model Registry yang menandai "versi aktif" -- konvensi Milestone
# 2.1, dipakai bersama batch DAG dan real-time API (menggantikan Stage yang
# deprecated). Lihat docs/05-model-registry-contract/model-registry-contract.md
# dan milestones/2.1-fondasi-orchestrator-model-registry/decisions.md Keputusan #5.
ACTIVE_ALIAS = "champion"

DEFAULT_TRACKING_URI = "sqlite:///mlruns.db"


def get_tracking_uri() -> str:
    """Ambil MLflow tracking URI dari env var ``MLFLOW_TRACKING_URI``.

    Default ``DEFAULT_TRACKING_URI`` kalau tidak diset -- tidak pernah
    hardcode path absolut supaya package tetap bisa dipanggil dari
    environment/proyek berbeda (KK1) tanpa mengubah kode.
    """
    return os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)
