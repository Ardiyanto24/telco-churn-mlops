"""Integration test -- Milestone 2.4 Checkpoint 1: round-trip
`record_run()`/`read_recent_baseline()` terhadap `quality.gate_run_history`
SUNGGUHAN di Supabase (pola sama test integrasi M1.5, mis.
`tests/inference/test_e2e_parity.py`).

Skip otomatis kalau `QUALITY_GATE_DB_URL`/`SUPABASE_DB_URL` tidak ada di
`.env`/environment.
"""

import os
import uuid
from pathlib import Path

import psycopg2
import pytest

from churn_prediction.quality import baseline

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


QUALITY_GATE_DB_URL = _load_env_var("QUALITY_GATE_DB_URL")
SUPABASE_DB_URL = _load_env_var("SUPABASE_DB_URL")  # admin, dipakai cleanup saja

pytestmark = pytest.mark.skipif(
    not QUALITY_GATE_DB_URL or not SUPABASE_DB_URL,
    reason="butuh QUALITY_GATE_DB_URL dan SUPABASE_DB_URL di .env",
)


@pytest.fixture
def source_table_tag():
    """Tag `source_table` unik per test -- supaya test yang jalan paralel/berulang
    tidak saling bentrok baseline-nya. Dibersihkan lewat koneksi admin sesudahnya
    (`quality_gate` sengaja tidak punya privilege DELETE -- append-only)."""
    tag = f"_test_baseline_{uuid.uuid4().hex[:8]}"
    yield tag
    admin_conn = psycopg2.connect(SUPABASE_DB_URL)
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        cur.execute("DELETE FROM quality.gate_run_history WHERE source_table = %s;", (tag,))
    admin_conn.close()


def test_record_run_returns_id(source_table_tag):
    run_id = baseline.record_run(
        source_table=source_table_tag,
        row_count=594194,
        null_proportions={"tenure": 0.0, "MonthlyCharges": 0.0},
        category_distributions={"Contract": {"Month-to-month": 0.503}},
        verdict="pass",
        connection_string=QUALITY_GATE_DB_URL,
    )
    assert isinstance(run_id, int)


def test_read_recent_baseline_returns_none_when_insufficient_history(source_table_tag):
    baseline.record_run(
        source_table=source_table_tag,
        row_count=594194,
        null_proportions={},
        category_distributions={},
        verdict="pass",
        connection_string=QUALITY_GATE_DB_URL,
    )
    baseline.record_run(
        source_table=source_table_tag,
        row_count=594100,
        null_proportions={},
        category_distributions={},
        verdict="pass",
        connection_string=QUALITY_GATE_DB_URL,
    )
    # cuma 2 run -- di bawah MIN_RUNS_FOR_BASELINE (3)
    result = baseline.read_recent_baseline(source_table_tag, connection_string=QUALITY_GATE_DB_URL)
    assert result is None


def test_read_recent_baseline_returns_rows_when_enough_history(source_table_tag):
    for i in range(4):
        baseline.record_run(
            source_table=source_table_tag,
            row_count=594194 - i,
            null_proportions={"tenure": 0.0},
            category_distributions={"Contract": {"Month-to-month": 0.5}},
            verdict="pass",
            details={"seq": i},
            connection_string=QUALITY_GATE_DB_URL,
        )

    result = baseline.read_recent_baseline(source_table_tag, n_runs=7, connection_string=QUALITY_GATE_DB_URL)

    assert result is not None
    assert len(result) == 4
    # jsonb round-trip: dict harus tetap dict (bukan string mentah)
    assert result[0]["null_proportions"] == {"tenure": 0.0}
    assert result[0]["category_distributions"] == {"Contract": {"Month-to-month": 0.5}}
    # terurut terbaru dulu -- run_at menurun
    run_ats = [row["run_at"] for row in result]
    assert run_ats == sorted(run_ats, reverse=True)


def test_read_recent_baseline_respects_n_runs_limit(source_table_tag):
    for i in range(5):
        baseline.record_run(
            source_table=source_table_tag,
            row_count=100 + i,
            null_proportions={},
            category_distributions={},
            verdict="pass",
            connection_string=QUALITY_GATE_DB_URL,
        )

    result = baseline.read_recent_baseline(source_table_tag, n_runs=3, connection_string=QUALITY_GATE_DB_URL)
    assert result is not None
    assert len(result) == 3
