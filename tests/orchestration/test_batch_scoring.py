"""Integration test -- Milestone 2.5 Checkpoint 3: parity, traceability lineage,
dan kegagalan terkontrol (rollback+retry) untuk `batch_scoring_flow`.

Skip otomatis kalau kredensial least-privilege (`BATCH_READER_DB_URL`,
`BATCH_WRITER_DB_URL`) atau `SUPABASE_DB_URL`/`MLFLOW_TRACKING_URI` tidak ada
di `.env`/environment.
"""

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import psycopg2
import pytest

from churn_prediction.inference.predictor import predict_active
from churn_prediction.schema.column_mapping import RAW_PASCAL_TO_SNAKE
from orchestration.flows import batch_scoring
from orchestration.flows.batch_scoring import (
    batch_scoring_flow,
    extract_raw_data,
    write_predictions,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
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
BATCH_READER_DB_URL = _load_env_var("BATCH_READER_DB_URL")
BATCH_WRITER_DB_URL = _load_env_var("BATCH_WRITER_DB_URL")

pytestmark = pytest.mark.skipif(
    not SUPABASE_DB_URL or not BATCH_READER_DB_URL or not BATCH_WRITER_DB_URL,
    reason="butuh SUPABASE_DB_URL, BATCH_READER_DB_URL, BATCH_WRITER_DB_URL di .env",
)


def _cleanup_batch_run(batch_run_id):
    conn = psycopg2.connect(SUPABASE_DB_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM predictions.batch_predictions WHERE batch_run_id = %s;", (batch_run_id,)
        )
    conn.close()


def _reset_quality_gate_baseline():
    """Bersihkan `quality.gate_run_history` untuk `telco_customers_source` --
    test flow-level di file ini memakai tabel SUMBER SUNGGUHAN (bukan tag
    unik per test seperti tests/quality/), jadi baseline rolling gerbang
    kualitas data (M2.4) ikut terisi tiap run flow. Tanpa reset ini, run
    berturut-turut dengan skala beda (mis. limit=50 lalu limit=594194) akan
    saling mencemari baseline satu sama lain dan memicu verdict stop palsu
    -- ditemukan langsung saat verifikasi Checkpoint 3 (lihat
    milestones/2.5-batch-scoring-dag/logs.md)."""
    conn = psycopg2.connect(SUPABASE_DB_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM quality.gate_run_history WHERE source_table = 'telco_customers_source';")
    conn.close()


@pytest.fixture
def flow_result():
    """Jalankan `batch_scoring_flow` sungguhan (bukan `.fn()`) untuk sampel
    kecil, bersihkan baris hasil + baseline gerbang kualitas sesudah test."""
    _reset_quality_gate_baseline()
    result = batch_scoring_flow(limit=50)
    yield result
    _cleanup_batch_run(result["batch_run_id"])
    _reset_quality_gate_baseline()


# ── KK3: parity batch vs pemanggilan langsung ───────────────────────────────

def test_batch_predictions_match_direct_predict_active_call(flow_result):
    conn = psycopg2.connect(SUPABASE_DB_URL)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT customer_id, churn_probability, churn_label, model_version
        FROM predictions.batch_predictions
        WHERE batch_run_id = %s
        ORDER BY customer_id
        LIMIT 5;
        """,
        (flow_result["batch_run_id"],),
    )
    stored_rows = cur.fetchall()
    assert len(stored_rows) == 5

    cols = ["id"] + list(RAW_PASCAL_TO_SNAKE.keys())
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in cols)
    customer_ids = tuple(r[0] for r in stored_rows)
    cur.execute(f"SELECT {cols_sql} FROM telco_customers_source WHERE id IN %s ORDER BY id;", (customer_ids,))
    raw_rows = cur.fetchall()
    colnames = [d[0] for d in cur.description]
    conn.close()

    raw_df = pd.DataFrame(raw_rows, columns=colnames)
    features = raw_df.drop(columns=["id"]).rename(columns=RAW_PASCAL_TO_SNAKE)
    direct = predict_active(features, alias="champion")

    for i, (customer_id, stored_proba, stored_label, stored_version) in enumerate(stored_rows):
        assert direct["churn_probability"].iloc[i] == pytest.approx(stored_proba)
        assert int(direct["churn_label"].iloc[i]) == stored_label
        assert direct["model_version"].iloc[i] == stored_version


# ── KK4: lineage bisa ditelusuri balik ──────────────────────────────────────

def test_lineage_traces_back_to_real_mlflow_version(flow_result):
    from churn_prediction.inference import registry

    conn = psycopg2.connect(SUPABASE_DB_URL)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT customer_id, model_version, model_alias, source_table, batch_run_id, flow_run_id, predicted_at
        FROM predictions.batch_predictions
        WHERE batch_run_id = %s
        LIMIT 3;
        """,
        (flow_result["batch_run_id"],),
    )
    rows = cur.fetchall()
    conn.close()

    assert len(rows) == 3
    # resolve_alias_version() mengembalikan int (lihat mlflow ModelVersion.version),
    # sedangkan kolom model_version di Postgres bertipe text -- cast eksplisit.
    current_champion_version = str(registry.resolve_alias_version("champion"))

    for customer_id, model_version, model_alias, source_table, batch_run_id, flow_run_id, predicted_at in rows:
        assert model_alias == "champion"
        assert model_version == current_champion_version  # alias belum berpindah sejak run ini
        assert source_table == "telco_customers_source"
        assert str(batch_run_id) == flow_result["batch_run_id"]
        assert flow_run_id is not None  # tertelusur ke run Prefect yang menghasilkannya
        assert predicted_at is not None


# ── KK2: kegagalan terkontrol -- rollback penuh, tidak ada data setengah-tertulis ──

def test_write_predictions_rolls_back_fully_on_partial_failure():
    """Baris ke-N sengaja melanggar CHECK constraint (churn_label bukan 0/1) --
    seluruh transaksi harus rollback, TIDAK ADA baris yang ter-insert
    sebagian (KK2 Milestone 2.5)."""
    batch_run_id = str(uuid.uuid4())
    predictions = pd.DataFrame(
        [
            {"customer_id": 1, "churn_probability": 0.1, "churn_label": 0, "model_version": "1", "predicted_at": "2026-08-13T00:00:00+00:00"},
            {"customer_id": 2, "churn_probability": 0.2, "churn_label": 0, "model_version": "1", "predicted_at": "2026-08-13T00:00:00+00:00"},
            {"customer_id": 3, "churn_probability": 0.9, "churn_label": 99, "model_version": "1", "predicted_at": "2026-08-13T00:00:00+00:00"},  # invalid
        ]
    )

    with pytest.raises(psycopg2.Error):
        write_predictions.fn(
            predictions, "telco_customers_source", batch_run_id, "test-rollback",
            connection_string=BATCH_WRITER_DB_URL,
        )

    conn = psycopg2.connect(SUPABASE_DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM predictions.batch_predictions WHERE batch_run_id = %s;", (batch_run_id,))
    count = cur.fetchone()[0]
    conn.close()

    assert count == 0, "rollback gagal -- ada baris ter-insert sebagian"


# ── KK2: retry Prefect pada kegagalan transient ─────────────────────────────

def test_extract_raw_data_retries_on_transient_failure():
    """Simulasikan koneksi database gagal 2x lalu berhasil -- task dengan
    retry Prefect harus tetap sukses pada percobaan ke-3, bukan gagal total
    (KK2 -- 'retry sesuai konfigurasi')."""
    real_connect = psycopg2.connect
    call_count = {"n": 0}

    def flaky_connect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise psycopg2.OperationalError("simulasi koneksi terputus sesaat")
        return real_connect(*args, **kwargs)

    fast_retry_task = extract_raw_data.with_options(retries=3, retry_delay_seconds=0)

    with patch.object(batch_scoring.psycopg2, "connect", side_effect=flaky_connect):
        df = fast_retry_task(limit=10, connection_string=BATCH_READER_DB_URL)

    assert len(df) == 10
    assert call_count["n"] == 3, "seharusnya gagal 2x lalu berhasil di percobaan ke-3"
