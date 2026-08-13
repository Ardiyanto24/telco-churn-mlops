"""Verifikasi parity host vs container -- Milestone 3.1 (KK1 penuh + KK2).

Pola sama `verify_before_promotion.py` (M2.8): fungsi murni terpisah dari
`main()`, fetch sampel real via `BATCH_READER_DB_URL`, rename
`RAW_PASCAL_TO_SNAKE`. Beda tujuan: skrip ini BUKAN membandingkan
challenger vs champion (M2.8), tapi membandingkan hasil `predict_active()`
yang dijalankan di HOST vs di dalam CONTAINER pada sampel yang SAMA --
membuktikan environment (versi Python/library) container menghasilkan
angka identik, bukan korektnes model (itu sudah KK2 Milestone 1.5,
tertutup).

Dipanggil dua kali secara terpisah (host, lalu container) -- outputnya
(JSON ke stdout) dibandingkan manual/dengan script lain, BUKAN
membandingkan di dalam proses yang sama seperti verify_before_promotion.py.

`ORDER BY id LIMIT` menjamin kedua run (host, container) mengambil baris
persis sama -- tanpa ini, dua run bisa dapat sampel berbeda dan
comparison jadi tidak berarti.
"""

import json
import os
import sys

import pandas as pd
import psycopg2

from churn_prediction.inference.predictor import predict_active
from churn_prediction.schema.column_mapping import RAW_PASCAL_TO_SNAKE

SOURCE_TABLE = "telco_customers_source"
SAMPLE_SIZE = 1000


def _get_reader_connection_string() -> str:
    uri = os.environ.get("BATCH_READER_DB_URL")
    if not uri:
        raise RuntimeError("BATCH_READER_DB_URL tidak diset di environment")
    return uri


def _fetch_sample(limit: int) -> pd.DataFrame:
    cols = list(RAW_PASCAL_TO_SNAKE.keys())
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in cols)
    sql = f"SELECT {cols_sql} FROM {SOURCE_TABLE} ORDER BY id LIMIT %s"

    conn = psycopg2.connect(_get_reader_connection_string())
    try:
        return pd.read_sql(sql, conn, params=(limit,))
    finally:
        conn.close()


def run_smoke_test(df_features: pd.DataFrame) -> dict:
    """Panggil `predict_active()` publik dan kembalikan hasil terstruktur
    -- dipisah dari `main()` supaya bisa di-unit-test tanpa DB (mock
    `predict_active`)."""
    out = predict_active(df_features)
    return {
        "row_count": len(out),
        "model_version": out["model_version"].iloc[0],
        "churn_probability": out["churn_probability"].astype(float).tolist(),
        "churn_label": out["churn_label"].astype(int).tolist(),
    }


def main() -> int:
    df_raw = _fetch_sample(SAMPLE_SIZE)
    df_features = df_raw.rename(columns=RAW_PASCAL_TO_SNAKE)

    result = run_smoke_test(df_features)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
