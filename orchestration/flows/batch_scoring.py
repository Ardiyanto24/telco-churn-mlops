"""Batch Scoring DAG -- Milestone 2.5.

Rangkaian task dengan dependency eksplisit: extract -> gerbang kualitas data
(`churn_prediction.quality`, M2.4) -> score (`predict_active()`, M2.1/M2.5)
-> write (append-only, satu transaksi). Lihat
milestones/2.5-batch-scoring-dag/decisions.md.

Tiap task punya wrapper tipis `@task` (retry native Prefect) di atas fungsi
inti -- panggil `<task>.fn(...)` untuk memanggil logika langsung tanpa
tracking Prefect Cloud (dipakai test, lihat tests/orchestration/).
"""

import logging
import os
import uuid
from typing import Optional

import pandas as pd
import psycopg2
import psycopg2.extras
from prefect import flow, task
from prefect.exceptions import MissingContextError
from prefect.logging import get_run_logger
from prefect.runtime import flow_run

from churn_prediction.inference.predictor import predict_active
from churn_prediction.quality.gate import run_gate
from churn_prediction.schema.column_mapping import RAW_PASCAL_TO_SNAKE

SOURCE_TABLE = "telco_customers_source"
MODEL_NAME = "churn_prediction_model"
MODEL_ALIAS = "champion"

NUMERIC_COLUMNS = ["tenure", "MonthlyCharges", "TotalCharges"]
# 15 kolom kategorikal/biner/struktural -- 18 kolom fitur model total
# (NUMERIC_COLUMNS + CATEGORICAL_COLUMNS), "gender" dikecualikan (M2.2:
# bukan input fitur model, lihat milestones/2.2-klasifikasi-fitur-feature-store/
# decisions.md).
CATEGORICAL_COLUMNS = [c for c in RAW_PASCAL_TO_SNAKE if c not in NUMERIC_COLUMNS and c != "gender"]


def _get_logger():
    """``get_run_logger()`` butuh konteks run Prefect aktif -- tidak tersedia
    saat task dipanggil langsung lewat ``.fn(...)`` (dipakai test, lihat
    tests/orchestration/). Fallback ke `logging` standar supaya task tetap
    testable tanpa harus lewat Prefect Cloud."""
    try:
        return get_run_logger()
    except MissingContextError:
        return logging.getLogger(__name__)


def _get_reader_connection_string() -> str:
    uri = os.environ.get("BATCH_READER_DB_URL")
    if not uri:
        raise RuntimeError("BATCH_READER_DB_URL tidak diset di environment/.env")
    return uri


def _get_writer_connection_string() -> str:
    uri = os.environ.get("BATCH_WRITER_DB_URL")
    if not uri:
        raise RuntimeError("BATCH_WRITER_DB_URL tidak diset di environment/.env")
    return uri


@task(retries=3, retry_delay_seconds=10)
def extract_raw_data(limit: Optional[int] = None, connection_string: Optional[str] = None) -> pd.DataFrame:
    """Ambil ``id`` + 19 kolom fitur (PascalCase) dari ``telco_customers_source``
    lewat role least-privilege ``batch_reader``."""
    logger = _get_logger()
    cols = ["id"] + list(RAW_PASCAL_TO_SNAKE.keys())
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in cols)
    sql = f"SELECT {cols_sql} FROM {SOURCE_TABLE} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"

    conn = psycopg2.connect(connection_string or _get_reader_connection_string())
    try:
        df = pd.read_sql(sql, conn)
    finally:
        conn.close()

    logger.info(f"Extracted {len(df)} baris dari {SOURCE_TABLE}")
    return df


@task(retries=2, retry_delay_seconds=5)
def run_quality_gate_task(df: pd.DataFrame):
    """Jalankan gerbang kualitas data (M2.4) -- ``stop`` menghentikan flow
    (raise, task berikutnya tidak jalan), ``flag`` dicatat tapi flow lanjut."""
    logger = _get_logger()
    result = run_gate(df, SOURCE_TABLE, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS)

    if result.verdict == "stop":
        reasons = "; ".join(c.message for c in result.checks if c.verdict == "stop")
        raise RuntimeError(f"Gerbang kualitas data STOP -- scoring dibatalkan: {reasons}")
    if result.verdict == "flag":
        reasons = "; ".join(c.message for c in result.checks if c.verdict == "flag")
        logger.warning(f"Gerbang kualitas data FLAG (lanjut ke scoring): {reasons}")
    else:
        logger.info("Gerbang kualitas data PASS.")
    return result


@task(retries=3, retry_delay_seconds=10)
def score_batch(df: pd.DataFrame) -> pd.DataFrame:
    """Rename PascalCase->snake_case (``column_mapping.py``), panggil
    ``predict_active()`` (alias ``champion``) -- satu sumber kebenaran
    transformasi+model, tidak diimplementasikan ulang di sini."""
    logger = _get_logger()
    ids = df["id"]
    features = df.drop(columns=["id"]).rename(columns=RAW_PASCAL_TO_SNAKE)

    predictions = predict_active(features, alias=MODEL_ALIAS)
    predictions = predictions.copy()
    predictions.insert(0, "customer_id", ids.values)

    logger.info(f"Scored {len(predictions)} baris, model_version={predictions['model_version'].iloc[0]}")
    return predictions


@task(retries=3, retry_delay_seconds=10)
def write_predictions(
    predictions: pd.DataFrame,
    source_table: str,
    batch_run_id: str,
    flow_run_id: Optional[str] = None,
    connection_string: Optional[str] = None,
) -> int:
    """Tulis seluruh baris prediksi dalam SATU transaksi (all-or-nothing) --
    kegagalan di tengah proses rollback penuh, tidak meninggalkan data
    setengah-tertulis (KK2 Milestone 2.5)."""
    logger = _get_logger()
    rows = [
        (
            int(row.customer_id),
            float(row.churn_probability),
            int(row.churn_label),
            MODEL_NAME,
            str(row.model_version),
            MODEL_ALIAS,
            source_table,
            row.predicted_at,
            batch_run_id,
            flow_run_id,
        )
        for row in predictions.itertuples(index=False)
    ]

    conn = psycopg2.connect(connection_string or _get_writer_connection_string())
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO predictions.batch_predictions
                    (customer_id, churn_probability, churn_label, model_name,
                     model_version, model_alias, source_table, predicted_at,
                     batch_run_id, flow_run_id)
                VALUES %s
                """,
                rows,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info(f"Menulis {len(rows)} baris prediksi (batch_run_id={batch_run_id})")
    return len(rows)


@flow(name="milestone-2-5-batch-scoring")
def batch_scoring_flow(limit: Optional[int] = None) -> dict:
    logger = _get_logger()
    batch_run_id = str(uuid.uuid4())
    try:
        current_flow_run_id = str(flow_run.id)
    except Exception:
        current_flow_run_id = None

    df = extract_raw_data(limit=limit)
    run_quality_gate_task(df)
    predictions = score_batch(df)
    written = write_predictions(predictions, SOURCE_TABLE, batch_run_id, current_flow_run_id)

    logger.info(f"Batch scoring selesai: {written} baris ditulis, batch_run_id={batch_run_id}")
    return {"batch_run_id": batch_run_id, "rows_written": written}


if __name__ == "__main__":
    # BATCH_SCORING_LIMIT -- dipakai entrypoint GitHub Actions
    # (.github/workflows/batch-scoring.yml, KD-1) untuk run verifikasi
    # terkontrol tanpa argumen CLI; kosong/absen = skala penuh (perilaku
    # lama tidak berubah).
    _limit_env = os.environ.get("BATCH_SCORING_LIMIT")
    batch_scoring_flow(limit=int(_limit_env) if _limit_env else None)
