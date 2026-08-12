"""Integration test -- Milestone 2.4 Checkpoint 2: `run_gate()` end-to-end
terhadap `quality.gate_run_history` SUNGGUHAN di Supabase.

Skenario mengikuti KK sumber milestone (uji coba terkontrol -- lihat
milestones/2.4-gerbang-kualitas-data-harian/decisions.md untuk keterbatasan
data statis `telco_customers_source`, belum ada data harian organik):
(a) data normal -> pass, tidak ada false alert;
(b) volume anjlok drastis (sintetis) -> stop;
(c) NULL melonjak drastis pada kolom fitur (sintetis) -> stop;
(d) pergeseran distribusi kategori sedang (sintetis) -> flag, bukan stop;
(e) riwayat baseline kosong (<3 run) -> check dilewati, bukan false-flag.
"""

import os
import uuid
from pathlib import Path

import pandas as pd
import psycopg2
import pytest

from churn_prediction.quality.gate import run_gate

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
SUPABASE_DB_URL = _load_env_var("SUPABASE_DB_URL")

pytestmark = pytest.mark.skipif(
    not QUALITY_GATE_DB_URL or not SUPABASE_DB_URL,
    reason="butuh QUALITY_GATE_DB_URL dan SUPABASE_DB_URL di .env",
)

NUMERIC_COLUMNS = ["tenure", "MonthlyCharges"]
CATEGORICAL_COLUMNS = ["Contract"]


def _make_df(n_rows, contract_month_to_month_ratio=0.5, null_tenure_ratio=0.0):
    n_month = int(n_rows * contract_month_to_month_ratio)
    n_other = n_rows - n_month
    contracts = ["Month-to-month"] * n_month + ["One year"] * (n_other // 2) + ["Two year"] * (n_other - n_other // 2)
    df = pd.DataFrame({
        "tenure": [36] * n_rows,
        "MonthlyCharges": [65.0] * n_rows,
        "Contract": contracts[:n_rows],
    })
    n_null = int(n_rows * null_tenure_ratio)
    if n_null:
        df.loc[df.index[:n_null], "tenure"] = None
    return df


@pytest.fixture
def source_table_tag():
    tag = f"_test_gate_{uuid.uuid4().hex[:8]}"
    yield tag
    admin_conn = psycopg2.connect(SUPABASE_DB_URL)
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        cur.execute("DELETE FROM quality.gate_run_history WHERE source_table = %s;", (tag,))
    admin_conn.close()


def _seed_baseline(tag, n_runs=3, n_rows=1000, contract_ratio=0.5):
    for _ in range(n_runs):
        df = _make_df(n_rows, contract_month_to_month_ratio=contract_ratio)
        run_gate(
            df, tag, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS,
            connection_string=QUALITY_GATE_DB_URL,
        )


def test_normal_data_passes_no_false_alert(source_table_tag):
    _seed_baseline(source_table_tag, n_rows=1000, contract_ratio=0.5)

    today = _make_df(1000, contract_month_to_month_ratio=0.51)  # fluktuasi wajar
    result = run_gate(
        today, source_table_tag, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS,
        connection_string=QUALITY_GATE_DB_URL,
    )

    assert result.verdict == "pass"
    assert result.run_id is not None


def test_severe_volume_drop_stops(source_table_tag):
    _seed_baseline(source_table_tag, n_rows=1000)

    today = _make_df(100)  # anjlok 90%
    result = run_gate(
        today, source_table_tag, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS,
        connection_string=QUALITY_GATE_DB_URL,
    )

    assert result.verdict == "stop"
    volume_result = next(r for r in result.checks if r.check == "volume")
    assert volume_result.verdict == "stop"


def test_severe_null_spike_stops(source_table_tag):
    _seed_baseline(source_table_tag, n_rows=1000)

    today = _make_df(1000, null_tenure_ratio=0.15)  # 15% NULL di kolom fitur
    result = run_gate(
        today, source_table_tag, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS,
        connection_string=QUALITY_GATE_DB_URL,
    )

    assert result.verdict == "stop"
    null_result = next(r for r in result.checks if r.check == "null_proportion")
    assert null_result.verdict == "stop"


def test_moderate_category_shift_flags_not_stops(source_table_tag):
    _seed_baseline(source_table_tag, n_rows=1000, contract_ratio=0.50)

    # geser proporsi Month-to-month dari 0.50 -> 0.65 (15pt, di atas flag 10pt,
    # di bawah stop 30pt) -- tanpa perubahan volume/NULL yang memicu check lain.
    today = _make_df(1000, contract_month_to_month_ratio=0.65)
    result = run_gate(
        today, source_table_tag, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS,
        connection_string=QUALITY_GATE_DB_URL,
    )

    assert result.verdict == "flag"
    dist_result = next(r for r in result.checks if r.check == "category_distribution")
    assert dist_result.verdict == "flag"


def test_insufficient_baseline_history_does_not_false_flag(source_table_tag):
    # tanpa seeding -- riwayat kosong (<3 run)
    today = _make_df(1000)
    result = run_gate(
        today, source_table_tag, NUMERIC_COLUMNS, CATEGORICAL_COLUMNS,
        connection_string=QUALITY_GATE_DB_URL,
    )

    assert result.verdict == "pass"
    volume_result = next(r for r in result.checks if r.check == "volume")
    assert "belum cukup data" in volume_result.message
