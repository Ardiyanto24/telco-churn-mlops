"""Gerbang kualitas data OTOMATIS via CI/CD -- Milestone 2.7.

Beda dari task DAG `run_quality_gate_task` (M2.5, jadi bagian
`batch_scoring_flow`): script ini dipicu GitHub Actions tiap push (bukan
dijadwalkan bersama DAG), dan memanggil `run_gate()` dengan
``record_history=False`` -- verdict nyata terhadap data live
``telco_customers_source``, TANPA menulis baris ke
``quality.gate_run_history``. Mencegah pencemaran baseline yang dipakai DAG
produksi (root cause yang sudah 2x ditemukan M2.5/M2.6) sekaligus memenuhi
permintaan otomatisasi lewat GitHub Actions -- lihat
milestones/2.7-cicd-verifikasi-parity/decisions.md.

Exit code 0: verdict pass/flag. Exit code 1: verdict stop.
"""

import os
import sys

import pandas as pd
import psycopg2

from churn_prediction.quality.gate import run_gate
from churn_prediction.schema.column_mapping import RAW_PASCAL_TO_SNAKE

SOURCE_TABLE = "telco_customers_source"
NUMERIC_COLUMNS = ["tenure", "MonthlyCharges", "TotalCharges"]
CATEGORICAL_COLUMNS = [c for c in RAW_PASCAL_TO_SNAKE if c not in NUMERIC_COLUMNS and c != "gender"]


def _get_reader_connection_string() -> str:
    uri = os.environ.get("BATCH_READER_DB_URL")
    if not uri:
        raise RuntimeError("BATCH_READER_DB_URL tidak diset di environment")
    return uri


def _get_quality_gate_connection_string() -> str:
    uri = os.environ.get("QUALITY_GATE_DB_URL")
    if not uri:
        raise RuntimeError("QUALITY_GATE_DB_URL tidak diset di environment")
    return uri


def _fetch_raw_data() -> pd.DataFrame:
    cols = ["id"] + list(RAW_PASCAL_TO_SNAKE.keys())
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in cols)
    sql = f"SELECT {cols_sql} FROM {SOURCE_TABLE} ORDER BY id"

    conn = psycopg2.connect(_get_reader_connection_string())
    try:
        return pd.read_sql(sql, conn)
    finally:
        conn.close()


def main() -> int:
    # Kolom TETAP PascalCase mentah (TIDAK di-rename) -- pola sama
    # run_quality_gate_task() M2.5, yang menerima df dari extract_raw_data()
    # SEBELUM score_batch() melakukan rename ke snake_case untuk prediksi.
    df = _fetch_raw_data()

    result = run_gate(
        df,
        SOURCE_TABLE,
        NUMERIC_COLUMNS,
        CATEGORICAL_COLUMNS,
        connection_string=_get_quality_gate_connection_string(),
        record_history=False,
    )

    print(f"Gerbang kualitas data (non-recording): verdict={result.verdict}")
    for check in result.checks:
        print(f"  [{check.verdict}] {check.check}: {check.message}")

    if result.verdict == "stop":
        print("STOP -- data hari ini dianggap tidak wajar dibanding baseline.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
