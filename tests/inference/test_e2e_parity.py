"""Integration test -- KK2 Milestone 1.5: parity END-TO-END (`predict()` lewat
bundle+MLflow) terhadap ground truth `model_final.joblib`+`preprocessor.joblib`
asli dimuat LANGSUNG (tanpa bundle/MLflow), pada data real Supabase.

Perluasan langsung dari `tests/transform/test_parity_real_artifact.py` (M1.2
KK2, cuma preprocessing) -- di sini ditambah satu langkah lagi:
`model.predict_proba()` + threshold, sesuai KK2 M1.5 ("verifikasi akhir
end-to-end, bukan hanya per-fungsi seperti Milestone 1.4").

Skip otomatis kalau `SUPABASE_DB_URL` tidak ada di `.env`/environment atau
artifact asli (`artifacs/`) tidak ditemukan.
"""

import os
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from churn_prediction.inference import predictor, registry
from churn_prediction.inference.constants import THRESHOLD
from churn_prediction.schema.column_mapping import RAW_PASCAL_TO_SNAKE
from churn_prediction.transform.artifact_loader import load_original_preprocessor

REPO_ROOT = Path(__file__).resolve().parents[2]
PREPROCESSOR_PATH = REPO_ROOT / "artifacs" / "proprocessor" / "preprocessor.joblib"
MODEL_PATH = REPO_ROOT / "artifacs" / "model" / "model_final.joblib"
ENV_PATH = REPO_ROOT / ".env"


def _load_env_var(name):
    value = os.environ.get(name)
    if value:
        return value
    if not ENV_PATH.exists():
        return None
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return None


SUPABASE_DB_URL = _load_env_var("SUPABASE_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not SUPABASE_DB_URL or not PREPROCESSOR_PATH.exists() or not MODEL_PATH.exists(),
        reason="butuh SUPABASE_DB_URL (.env) dan artifacs/{proprocessor,model}",
    ),
    pytest.mark.integration,
]

def _fetch_real_rows(limit=1000):
    import psycopg2

    conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=15)
    cur = conn.cursor()
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in ["id"] + list(RAW_PASCAL_TO_SNAKE.keys()))
    cur.execute(f"SELECT {cols_sql} FROM telco_customers_source ORDER BY id LIMIT %s;", (limit,))
    colnames = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=colnames)
    df["MonthlyCharges"] = df["MonthlyCharges"].astype(float)
    df["TotalCharges"] = df["TotalCharges"].astype(float)
    return df


def test_kk2_e2e_parity_predict_vs_ground_truth(tmp_path):
    df_pascal = _fetch_real_rows(limit=1000)
    assert set([0, 1, 2]).issubset(set(df_pascal["id"].tolist())), (
        "sampel harus mencakup baris id=0,1,2 (rujukan notebook-audit.md H.2)"
    )
    df_pascal_features = df_pascal.drop(columns=["id"])

    # Ground truth: preprocessor.joblib + model_final.joblib asli, dimuat LANGSUNG
    # -- TANPA bundle/MLflow sama sekali.
    original_preprocessor = load_original_preprocessor(PREPROCESSOR_PATH)
    with warnings.catch_warnings():
        # InconsistentVersionWarning (sklearn) + UserWarning versi lama (xgboost) --
        # sudah diverifikasi tidak mempengaruhi validitas predict_proba(), lihat
        # milestones/1.5-inference-service/decisions.md Keputusan #9.
        warnings.simplefilter("ignore")
        model = joblib.load(MODEL_PATH)
    transformed_gt = original_preprocessor.transform(df_pascal_features)
    proba_gt = model.predict_proba(transformed_gt)[:, 1]
    label_gt = (proba_gt >= THRESHOLD).astype(int)

    # Kita: predict() publik lewat bundle+MLflow, input snake_case.
    df_snake = df_pascal_features.rename(columns=RAW_PASCAL_TO_SNAKE)
    tracking_uri = f"sqlite:///{tmp_path.as_posix()}/mlruns_test.db"
    bundle = registry.build_bundle()
    registry.register_model(bundle, tracking_uri=tracking_uri)
    out = predictor.predict(df_snake, model_version="1", tracking_uri=tracking_uri)

    proba_ours = out["churn_probability"].to_numpy(dtype=float)
    label_ours = out["churn_label"].to_numpy(dtype=int)

    assert np.allclose(proba_ours, proba_gt, rtol=1e-6, atol=1e-8), (
        f"Parity KK2 GAGAL (probability): {int((~np.isclose(proba_ours, proba_gt, rtol=1e-6, atol=1e-8)).sum())}"
        f"/{len(proba_gt)} baris beda"
    )
    assert (label_ours == label_gt).all(), "Parity KK2 GAGAL (label): ada baris churn_label berbeda"
