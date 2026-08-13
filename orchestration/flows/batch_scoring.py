"""Batch Scoring DAG -- Milestone 2.5, diperluas Milestone 2.9.

Rangkaian task dengan dependency eksplisit: extract -> gerbang kualitas data
(`churn_prediction.quality`, M2.4) -> score (`predict_active()`, M2.1/M2.5)
-> write (append-only, satu transaksi). Lihat
milestones/2.5-batch-scoring-dag/decisions.md.

Milestone 2.9 menambah dukungan `source_table=telco_customers_synthetic`
(identitas `customer_key` uuid, bukan `customer_id` int) berdampingan dengan
`telco_customers_source` (perilaku default, tidak berubah) -- lihat
milestones/2.9-otomatisasi-scoring-data-sintesis/decisions.md Keputusan #5.
Kolom `telco_customers_synthetic` SUDAH snake_case (`column_mapping.py`
mengikuti konvensinya), jadi tidak perlu rename PascalCase->snake_case
untuk path ini.

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
SYNTHETIC_TABLE = "telco_customers_synthetic"
MODEL_NAME = "churn_prediction_model"
MODEL_ALIAS = "champion"

NUMERIC_COLUMNS = ["tenure", "MonthlyCharges", "TotalCharges"]
# 15 kolom kategorikal/biner/struktural -- 18 kolom fitur model total
# (NUMERIC_COLUMNS + CATEGORICAL_COLUMNS), "gender" dikecualikan (M2.2:
# bukan input fitur model, lihat milestones/2.2-klasifikasi-fitur-feature-store/
# decisions.md). Nama sudah PascalCase telco_customers_source; sama persis
# dengan RAW_PASCAL_TO_SNAKE.values() dipakai untuk telco_customers_synthetic
# (M2.9) -- run_gate() TIDAK mengasumsikan konvensi nama kolom (M2.4).
CATEGORICAL_COLUMNS = [c for c in RAW_PASCAL_TO_SNAKE if c not in NUMERIC_COLUMNS and c != "gender"]


def _quality_gate_columns(source_table: str) -> tuple[list, list]:
    """``NUMERIC_COLUMNS``/``CATEGORICAL_COLUMNS`` di atas PascalCase --
    cocok untuk ``telco_customers_source`` (di-rename BELAKANGAN, di
    ``score_batch``). ``telco_customers_synthetic`` sudah snake_case SEJAK
    extract (M2.9) -- gerbang kualitas data (M2.4, agnostik nama kolom)
    butuh daftar kolom yang benar-benar ada di ``df`` yang diperiksa."""
    if source_table == SYNTHETIC_TABLE:
        numeric = [RAW_PASCAL_TO_SNAKE[c] for c in NUMERIC_COLUMNS]
        categorical = [RAW_PASCAL_TO_SNAKE[c] for c in CATEGORICAL_COLUMNS]
        return numeric, categorical
    return NUMERIC_COLUMNS, CATEGORICAL_COLUMNS


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


def _extract_from_source(source_table: str, limit: Optional[int], conn) -> pd.DataFrame:
    """``telco_customers_source`` -- PascalCase, identitas ``id`` (bigint).
    Perilaku identik Milestone 2.5, tidak berubah."""
    cols = ["id"] + list(RAW_PASCAL_TO_SNAKE.keys())
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in cols)
    sql = f"SELECT {cols_sql} FROM {source_table} ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return pd.read_sql(sql, conn)


def _extract_from_synthetic(source_table: str, generation_id: str, limit: Optional[int], conn) -> pd.DataFrame:
    """``telco_customers_synthetic`` -- SUDAH snake_case, identitas
    ``customer_key`` (uuid). Difilter ke satu ``generation_id`` -- satu run
    generator = satu event trigger (M2.9 Keputusan #5), bukan "semua baris
    belum diproses" lewat state terpisah."""
    cols = ["customer_key"] + list(RAW_PASCAL_TO_SNAKE.values())
    cols_sql = ", ".join(cols)
    sql = f"SELECT {cols_sql} FROM {source_table} WHERE generation_id = %(generation_id)s ORDER BY synthetic_id"
    params = {"generation_id": generation_id}
    if limit:
        sql += " LIMIT %(limit)s"
        params["limit"] = int(limit)
    return pd.read_sql(sql, conn, params=params)


@task(retries=3, retry_delay_seconds=10)
def extract_raw_data(
    source_table: str = SOURCE_TABLE,
    generation_id: Optional[str] = None,
    limit: Optional[int] = None,
    connection_string: Optional[str] = None,
) -> pd.DataFrame:
    """Ambil data mentah dari ``source_table`` lewat role least-privilege
    ``batch_reader`` (diperluas M2.9 untuk mencakup ``telco_customers_synthetic``,
    lihat infra/sql/2.9_synthetic_reader_grant.sql)."""
    logger = _get_logger()
    conn = psycopg2.connect(connection_string or _get_reader_connection_string())
    try:
        if source_table == SYNTHETIC_TABLE:
            if not generation_id:
                raise ValueError("generation_id wajib diisi saat source_table=telco_customers_synthetic")
            df = _extract_from_synthetic(source_table, generation_id, limit, conn)
        else:
            df = _extract_from_source(source_table, limit, conn)
    finally:
        conn.close()

    logger.info(f"Extracted {len(df)} baris dari {source_table}")
    return df


@task(retries=2, retry_delay_seconds=5)
def run_quality_gate_task(df: pd.DataFrame, source_table: str = SOURCE_TABLE):
    """Jalankan gerbang kualitas data (M2.4) -- ``stop`` menghentikan flow
    (raise, task berikutnya tidak jalan), ``flag`` dicatat tapi flow lanjut.
    Baseline rolling ter-key per ``source_table`` (M2.4 didesain agnostik
    nama tabel) -- run pertama untuk ``telco_customers_synthetic`` (0 riwayat)
    PASS wajar, ditafsirkan "belum cukup data" bukan anomali."""
    logger = _get_logger()
    numeric_columns, categorical_columns = _quality_gate_columns(source_table)
    result = run_gate(df, source_table, numeric_columns, categorical_columns)

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
    """Rename PascalCase->snake_case (``column_mapping.py``, no-op untuk
    kolom yang sudah snake_case -- lihat docstring modul), panggil
    ``predict_active()`` (alias ``champion``) -- satu sumber kebenaran
    transformasi+model, tidak diimplementasikan ulang di sini.

    Mendeteksi kolom identitas dari ``df`` (``customer_key`` uuid untuk
    synthetic, ``id`` bigint untuk source) -- hasil selalu punya KEDUA
    kolom ``customer_id``/``customer_key``, salah satu ``None`` (M2.9
    Keputusan #2, exactly-one-identity)."""
    logger = _get_logger()
    is_synthetic = "customer_key" in df.columns
    identity_col = "customer_key" if is_synthetic else "id"
    ids = df[identity_col]
    features = df.drop(columns=[identity_col]).rename(columns=RAW_PASCAL_TO_SNAKE)

    predictions = predict_active(features, alias=MODEL_ALIAS)
    predictions = predictions.copy()
    if is_synthetic:
        predictions.insert(0, "customer_id", None)
        predictions.insert(1, "customer_key", ids.values)
    else:
        predictions.insert(0, "customer_id", ids.values)
        predictions.insert(1, "customer_key", None)

    logger.info(f"Scored {len(predictions)} baris, model_version={predictions['model_version'].iloc[0]}")
    return predictions


@task(retries=3, retry_delay_seconds=10)
def write_predictions(
    predictions: pd.DataFrame,
    source_table: str,
    batch_run_id: str,
    flow_run_id: Optional[str] = None,
    generation_id: Optional[str] = None,
    connection_string: Optional[str] = None,
) -> int:
    """Tulis seluruh baris prediksi dalam SATU transaksi (all-or-nothing) --
    kegagalan di tengah proses rollback penuh, tidak meninggalkan data
    setengah-tertulis (KK2 Milestone 2.5).

    Backward-compatible dengan ``predictions`` yang HANYA punya kolom
    ``customer_id`` (tanpa ``customer_key`` sama sekali) -- dipakai test
    existing (``tests/orchestration/test_batch_scoring.py``). ``generation_id``
    parameter tunggal per-write (satu flow run = satu generation_id untuk
    path synthetic), bukan kolom per-baris."""
    logger = _get_logger()
    has_customer_key = "customer_key" in predictions.columns
    rows = []
    for row in predictions.itertuples(index=False):
        customer_id = getattr(row, "customer_id", None)
        if customer_id is not None and pd.isna(customer_id):
            customer_id = None
        customer_key = getattr(row, "customer_key", None) if has_customer_key else None
        if customer_key is not None and pd.isna(customer_key):
            customer_key = None
        rows.append(
            (
                int(customer_id) if customer_id is not None else None,
                str(customer_key) if customer_key is not None else None,
                float(row.churn_probability),
                int(row.churn_label),
                MODEL_NAME,
                str(row.model_version),
                MODEL_ALIAS,
                source_table,
                row.predicted_at,
                batch_run_id,
                flow_run_id,
                generation_id,
            )
        )

    conn = psycopg2.connect(connection_string or _get_writer_connection_string())
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO predictions.batch_predictions
                    (customer_id, customer_key, churn_probability, churn_label, model_name,
                     model_version, model_alias, source_table, predicted_at,
                     batch_run_id, flow_run_id, generation_id)
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
def batch_scoring_flow(
    limit: Optional[int] = None,
    source_table: str = SOURCE_TABLE,
    generation_id: Optional[str] = None,
) -> dict:
    logger = _get_logger()
    batch_run_id = str(uuid.uuid4())
    try:
        current_flow_run_id = str(flow_run.id)
    except Exception:
        current_flow_run_id = None

    df = extract_raw_data(source_table=source_table, generation_id=generation_id, limit=limit)
    run_quality_gate_task(df, source_table=source_table)
    predictions = score_batch(df)
    written = write_predictions(
        predictions, source_table, batch_run_id, current_flow_run_id, generation_id=generation_id
    )

    logger.info(f"Batch scoring selesai: {written} baris ditulis, batch_run_id={batch_run_id}")
    return {"batch_run_id": batch_run_id, "rows_written": written}


if __name__ == "__main__":
    # BATCH_SCORING_LIMIT -- dipakai entrypoint GitHub Actions
    # (.github/workflows/batch-scoring.yml, KD-1) untuk run verifikasi
    # terkontrol tanpa argumen CLI; kosong/absen = skala penuh (perilaku
    # lama tidak berubah).
    # BATCH_SOURCE_TABLE/BATCH_GENERATION_ID -- dipakai entrypoint
    # .github/workflows/synthetic-auto-scoring.yml (M2.9, trigger
    # repository_dispatch) supaya source_table/generation_id bisa diisi
    # tanpa argumen CLI. Default BATCH_SOURCE_TABLE = SOURCE_TABLE, perilaku
    # lama (telco_customers_source) tidak berubah kalau env var ini absen.
    _limit_env = os.environ.get("BATCH_SCORING_LIMIT")
    _source_table_env = os.environ.get("BATCH_SOURCE_TABLE", SOURCE_TABLE)
    _generation_id_env = os.environ.get("BATCH_GENERATION_ID")
    batch_scoring_flow(
        limit=int(_limit_env) if _limit_env else None,
        source_table=_source_table_env,
        generation_id=_generation_id_env,
    )
