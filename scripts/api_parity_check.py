"""Verifikasi KK1+KK4 (parity) Milestone 3.2 -- Real-Time Inference API.

Ground truth: baris `predictions.batch_predictions` yang SUDAH tersimpan
dari batch scoring (Milestone 2.5), BUKAN re-run batch baru (lihat
milestones/3.2-real-time-inference-api/decisions.md Keputusan #9). Sampel
diambil dari `customer_id` yang sudah di-score dengan `model_version` SAMA
PERSIS dengan versi champion AKTIF saat ini (`resolve_alias_version()`) --
kalau baris tersimpan berasal dari versi lama (mis. sisa uji rollback M2.8),
perbandingan tidak valid (API akan menghasilkan angka BEDA secara SAH, bukan
bug) -- filter ini eksplisit supaya tidak salah simpul.

Untuk tiap baris: fetch fitur mentah dari `telco_customers_source`, kirim ke
API real-time (`POST /predict`), bandingkan `churn_probability`
(`np.allclose`), `churn_label` (exact), `model_version` (exact) terhadap
baris tersimpan.
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
import psycopg2
import requests

from churn_prediction.inference.constants import ACTIVE_ALIAS
from churn_prediction.inference.registry import resolve_alias_version
from churn_prediction.schema.column_mapping import RAW_PASCAL_TO_SNAKE

SOURCE_TABLE = "telco_customers_source"
SAMPLE_SIZE = 20
INT_FIELDS = {"tenure", "senior_citizen"}
FLOAT_FIELDS = {"monthly_charges", "total_charges"}


def _fetch_ground_truth(limit: int, model_version: str) -> pd.DataFrame:
    conn = psycopg2.connect(os.environ["BATCH_WRITER_DB_URL"])
    try:
        sql = """
            SELECT DISTINCT ON (customer_id) customer_id, churn_probability, churn_label, model_version
            FROM predictions.batch_predictions
            WHERE source_table = %s AND model_version = %s
            ORDER BY customer_id, predicted_at DESC
            LIMIT %s
        """
        return pd.read_sql(sql, conn, params=(SOURCE_TABLE, model_version, limit))
    finally:
        conn.close()


def _fetch_raw_features(customer_ids: list) -> pd.DataFrame:
    cols = list(RAW_PASCAL_TO_SNAKE.keys())
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in ["id"] + cols)
    conn = psycopg2.connect(os.environ["BATCH_READER_DB_URL"])
    try:
        sql = f"SELECT {cols_sql} FROM {SOURCE_TABLE} WHERE id = ANY(%s)"
        df = pd.read_sql(sql, conn, params=(customer_ids,))
        df["MonthlyCharges"] = df["MonthlyCharges"].astype(float)
        df["TotalCharges"] = df["TotalCharges"].astype(float)
        return df.set_index("id")
    finally:
        conn.close()


def _row_to_payload(row: pd.Series) -> dict:
    payload = {}
    for pascal_col, snake_col in RAW_PASCAL_TO_SNAKE.items():
        value = row[pascal_col]
        if snake_col in INT_FIELDS:
            payload[snake_col] = int(value)
        elif snake_col in FLOAT_FIELDS:
            payload[snake_col] = float(value)
        else:
            payload[snake_col] = str(value)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--limit", type=int, default=SAMPLE_SIZE)
    args = parser.parse_args()

    # str() eksplisit -- resolve_alias_version() mengembalikan int, sementara
    # kolom predictions.batch_predictions.model_version bertipe text (sama
    # seperti _attach_lineage() di predictor.py yang juga menstringkan nilai
    # ini sebelum ditulis/dipakai lineage).
    active_version = str(resolve_alias_version(ACTIVE_ALIAS))
    print(f"Versi champion aktif saat ini: {active_version}")

    ground_truth = _fetch_ground_truth(args.limit, active_version)
    if ground_truth.empty:
        print(
            f"Tidak ada baris predictions.batch_predictions dengan model_version={active_version} "
            f"untuk {SOURCE_TABLE}",
            file=sys.stderr,
        )
        return 1
    print(f"Ground truth: {len(ground_truth)} baris (model_version={active_version})")

    raw_by_id = _fetch_raw_features(ground_truth["customer_id"].tolist())

    api_probs, api_labels, api_versions = [], [], []
    for customer_id in ground_truth["customer_id"]:
        payload = _row_to_payload(raw_by_id.loc[customer_id])
        response = requests.post(f"{args.api_url}/predict", json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        api_probs.append(body["churn_probability"])
        api_labels.append(body["churn_label"])
        api_versions.append(body["model_version"])

    api_probs = np.array(api_probs)
    api_labels = np.array(api_labels)
    gt_probs = ground_truth["churn_probability"].to_numpy(dtype=float)
    gt_labels = ground_truth["churn_label"].to_numpy(dtype=int)

    proba_match = np.allclose(api_probs, gt_probs, rtol=1e-6, atol=1e-8)
    label_match = bool((api_labels == gt_labels).all())
    version_match = all(v == active_version for v in api_versions)
    max_diff = float(np.max(np.abs(api_probs - gt_probs)))

    print(f"churn_probability allclose(rtol=1e-6): {proba_match} (diff maksimum: {max_diff})")
    print(f"churn_label exact match: {label_match}")
    print(f"model_version match: {version_match}")

    if proba_match and label_match and version_match:
        print("KK1+KK4 PASS: parity API real-time vs batch (M2.5) terbukti.")
        return 0
    print("KK1+KK4 FAIL: parity tidak cocok.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
