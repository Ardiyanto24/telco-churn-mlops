"""Komputasi drift dua tingkat (PSI + KS-test/Chi-square) -- Milestone 3.6.

Mode ``baseline``: sample ACAK N baris dari ``telco_customers_source``
(baseline data training TETAP, byte-identik data training --
notebook-audit.md Bagian H.2), transform via
``registry.load_active_pipeline()``, skor via ``predict_active()``, tulis ke
``drift.baseline_sample``. Dijalankan SEKALI secara lokal (bukan CI --
baseline tidak berubah kecuali model di-retrain, lihat
milestones/3.6-monitoring-drift-kualitas-model/decisions.md Keputusan #5).

Mode ``current``: baca ``drift.baseline_sample`` (harus sudah ada), baca
SELURUH ``telco_customers_synthetic`` (transform, SUDAH snake_case), baca
``predictions.batch_predictions WHERE source_table='telco_customers_synthetic'``
(output SUDAH discor Milestone 2.9 -- tidak perlu re-score), hitung PSI+
KS/Chi-square untuk 29 fitur + 1 output, tulis ``drift.drift_check_results``.
Dijalankan berkala via ``.github/workflows/drift-monitoring.yml`` (trigger
``workflow_run`` setelah ``synthetic-auto-scoring`` selesai).

``--override-current <path-json>`` -- untuk uji coba terkontrol (KK1 M3.6):
baca nilai current-window dari file JSON (``{"feature_name": [angka, ...]}``)
utk fitur yang disebut, TIDAK menyentuh tabel produksi
``telco_customers_synthetic``. Fitur yang TIDAK disebut tetap pakai data
sungguhan.

Murni OBSERVASIONAL -- TIDAK mengubah ``orchestration/flows/batch_scoring.py``
maupun workflow ``.github/workflows/synthetic-auto-scoring.yml`` (Keputusan
#3 M3.6).
"""

import argparse
import json
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

from churn_prediction.drift.constants import (
    BASELINE_SAMPLE_SIZE,
    FEATURE_TYPES,
    PREDICTION_OUTPUT_NAME,
    PREDICTION_OUTPUT_TYPE,
)
from churn_prediction.drift.metrics import combined_verdict, compute_psi, compute_tier2_pvalue
from churn_prediction.inference.predictor import predict_active
from churn_prediction.inference.registry import load_active_pipeline
from churn_prediction.schema.column_mapping import RAW_PASCAL_TO_SNAKE

SOURCE_TABLE = "telco_customers_source"
SYNTHETIC_TABLE = "telco_customers_synthetic"


def _writer_connection_string() -> str:
    uri = os.environ.get("DRIFT_WRITER_DB_URL")
    if not uri:
        raise RuntimeError("DRIFT_WRITER_DB_URL tidak diset di environment/.env")
    return uri


def _fetch_baseline_raw_sample(conn, n: int) -> pd.DataFrame:
    """Sample ACAK n baris dari telco_customers_source -- ORDER BY random()
    cukup untuk kebutuhan one-time sampling (bukan hot path)."""
    cols = ["id"] + list(RAW_PASCAL_TO_SNAKE.keys())
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in cols)
    sql = f"SELECT {cols_sql} FROM {SOURCE_TABLE} ORDER BY random() LIMIT %s"
    return pd.read_sql(sql, conn, params=(n,))


def _fetch_current_synthetic(conn) -> pd.DataFrame:
    """SELURUH baris telco_customers_synthetic saat ini -- SUDAH snake_case
    (M2.9), tidak perlu rename."""
    cols = ["customer_key"] + list(RAW_PASCAL_TO_SNAKE.values())
    cols_sql = ", ".join(cols)
    return pd.read_sql(f"SELECT {cols_sql} FROM {SYNTHETIC_TABLE}", conn)


def _fetch_current_predictions(conn) -> pd.DataFrame:
    sql = "SELECT churn_probability FROM predictions.batch_predictions WHERE source_table = %s"
    return pd.read_sql(sql, conn, params=(SYNTHETIC_TABLE,))


def _fetch_baseline_grouped(conn) -> dict:
    df = pd.read_sql("SELECT feature_name, value FROM drift.baseline_sample", conn)
    if df.empty:
        raise RuntimeError("drift.baseline_sample kosong -- jalankan --mode baseline dulu")
    return {name: group["value"].to_numpy() for name, group in df.groupby("feature_name")}


def run_baseline(n: int = BASELINE_SAMPLE_SIZE) -> None:
    conn = psycopg2.connect(_writer_connection_string())
    try:
        df_raw = _fetch_baseline_raw_sample(conn, n)
        features = df_raw.drop(columns=["id"]).rename(columns=RAW_PASCAL_TO_SNAKE)

        pipeline = load_active_pipeline()
        transformed = pipeline.transform(features)
        predictions = predict_active(features)

        rows = [
            (feature_name, float(value))
            for feature_name in transformed.columns
            for value in transformed[feature_name].to_numpy()
        ]
        rows += [
            (PREDICTION_OUTPUT_NAME, float(value))
            for value in predictions["churn_probability"].to_numpy()
        ]

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO drift.baseline_sample (feature_name, value) VALUES %s",
                rows,
            )
        conn.commit()
        print(f"Baseline computed: {len(rows)} baris ({len(transformed.columns)} fitur + 1 output) x sample={n}")
    finally:
        conn.close()


def run_current(override_path: Optional[str] = None) -> None:
    conn = psycopg2.connect(_writer_connection_string())
    try:
        baseline_by_feature = _fetch_baseline_grouped(conn)

        df_synthetic = _fetch_current_synthetic(conn)
        pipeline = load_active_pipeline()
        transformed_current = pipeline.transform(df_synthetic.drop(columns=["customer_key"]))
        current_by_feature = {col: transformed_current[col].to_numpy() for col in transformed_current.columns}

        preds = _fetch_current_predictions(conn)
        current_by_feature[PREDICTION_OUTPUT_NAME] = preds["churn_probability"].to_numpy()

        sample_size_current = len(df_synthetic)

        if override_path:
            with open(override_path, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            for feature_name, values in overrides.items():
                current_by_feature[feature_name] = np.array(values)
            print(f"Override AKTIF ({override_path}): {list(overrides.keys())}")

        all_feature_names = list(FEATURE_TYPES.keys()) + [PREDICTION_OUTPUT_NAME]
        rows = []
        for feature_name in all_feature_names:
            feature_type = FEATURE_TYPES.get(feature_name, PREDICTION_OUTPUT_TYPE)
            baseline_values = baseline_by_feature[feature_name]
            current_values = current_by_feature[feature_name]

            psi = compute_psi(baseline_values, current_values, feature_type=feature_type)
            pvalue = compute_tier2_pvalue(baseline_values, current_values, feature_type=feature_type)
            statistical_test = "ks" if feature_type == "numeric" else "chi2"
            verdict = combined_verdict(psi, pvalue)

            rows.append(
                (feature_name, feature_type, psi, statistical_test, pvalue, verdict, sample_size_current)
            )

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO drift.drift_check_results "
                "(feature_name, feature_type, psi, statistical_test, p_value, verdict, sample_size_current) "
                "VALUES %s",
                rows,
            )
        conn.commit()
        print(f"Current-window computed: {len(rows)} baris (29 fitur + 1 output)")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["baseline", "current"], required=True)
    parser.add_argument("--sample-size", type=int, default=BASELINE_SAMPLE_SIZE)
    parser.add_argument(
        "--override-current",
        type=str,
        default=None,
        help="Path JSON override nilai current-window (uji coba terkontrol, mode=current saja)",
    )
    args = parser.parse_args()

    if args.mode == "baseline":
        run_baseline(n=args.sample_size)
    else:
        run_current(override_path=args.override_current)
    return 0


if __name__ == "__main__":
    sys.exit(main())
