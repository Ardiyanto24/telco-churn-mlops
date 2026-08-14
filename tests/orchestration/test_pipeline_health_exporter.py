"""Unit test -- Milestone 3.5 Checkpoint 2: exporter status pipeline batch.

Seluruh test di sini pakai mock (Prefect client + DB engine/koneksi) --
TIDAK butuh kredensial sungguhan (beda dari tests/orchestration/test_batch_scoring.py
yang integration). Verifikasi manual terhadap Prefect Cloud + Postgres NYATA
sudah dilakukan terpisah saat implementasi (dicatat di
milestones/3.5-monitoring-infra-pipeline-health/logs.md), test ini menjaga
regresi lewat mock supaya tidak butuh network di CI.
"""

import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

from orchestration.monitoring import pipeline_health_exporter as exporter


def _make_flow_run(state_type: str = "COMPLETED", duration_seconds: float = 4.2, end_time=None):
    run = MagicMock()
    run.state_type = MagicMock(value=state_type)
    run.total_run_time = dt.timedelta(seconds=duration_seconds)
    run.end_time = end_time or dt.datetime(2026, 8, 14, 4, 1, 51, tzinfo=dt.timezone.utc)
    return run


class _FakeClientContext:
    def __init__(self, runs):
        self._runs = runs

    async def __aenter__(self):
        client = MagicMock()
        client.read_flow_runs = AsyncMock(return_value=self._runs)
        return client

    async def __aexit__(self, *exc_info):
        return False


# ── get_latest_flow_run() ───────────────────────────────────────────────────


def test_get_latest_flow_run_returns_none_when_no_runs():
    with patch.object(exporter, "get_client", return_value=_FakeClientContext([])):
        result = asyncio.run(exporter.get_latest_flow_run("some-flow"))
    assert result is None


def test_get_latest_flow_run_returns_details_when_run_exists():
    run = _make_flow_run(state_type="COMPLETED", duration_seconds=4.2)
    with patch.object(exporter, "get_client", return_value=_FakeClientContext([run])):
        result = asyncio.run(exporter.get_latest_flow_run("milestone-2-5-batch-scoring"))
    assert result["state_type"] == "COMPLETED"
    assert result["duration_seconds"] == 4.2
    assert result["end_time_epoch"] == run.end_time.timestamp()


def test_flow_status_value_mapping():
    assert exporter._flow_status_value("COMPLETED") == 1.0
    assert exporter._flow_status_value("FAILED") == 0.0
    assert exporter._flow_status_value("CRASHED") == 0.0
    assert exporter._flow_status_value(None) == -1.0


# ── get_quality_gate_status() / get_write_staleness() ───────────────────────


def _mock_engine(rows):
    engine = MagicMock()
    conn = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    conn.execute.return_value = result
    engine.connect.return_value.__enter__.return_value = conn
    return engine


def test_get_quality_gate_status_groups_by_source_table():
    row_a = MagicMock(source_table="telco_customers_source", verdict="pass")
    row_b = MagicMock(source_table="telco_customers_synthetic", verdict="flag")
    engine = _mock_engine([row_a, row_b])

    result = exporter.get_quality_gate_status(engine)

    assert result == {"telco_customers_source": "pass", "telco_customers_synthetic": "flag"}


def test_get_write_staleness_returns_age_per_source_table():
    row = MagicMock(source_table="telco_customers_source", age_seconds=123.456)
    engine = _mock_engine([row])

    result = exporter.get_write_staleness(engine)

    assert result == {"telco_customers_source": 123.456}


# ── refresh_once() -- wiring gauge dari ketiga sinyal ───────────────────────


def test_refresh_once_sets_all_gauges_on_success():
    run = _make_flow_run(state_type="COMPLETED", duration_seconds=7.5)
    engine = _mock_engine([])  # dipanggil 2x (quality gate, staleness) -- override per-call di bawah

    quality_row = MagicMock(source_table="telco_customers_source", verdict="pass")
    staleness_row = MagicMock(source_table="telco_customers_source", age_seconds=99.0)

    with (
        patch.object(exporter, "get_client", return_value=_FakeClientContext([run])),
        patch.object(exporter, "get_quality_gate_status", return_value={"telco_customers_source": "pass"}),
        patch.object(exporter, "get_write_staleness", return_value={"telco_customers_source": 99.0}),
    ):
        exporter.refresh_once(engine, flow_name="milestone-2-5-batch-scoring")

    assert exporter.FLOW_LAST_STATUS.labels(flow_name="milestone-2-5-batch-scoring")._value.get() == 1.0
    assert exporter.FLOW_LAST_DURATION_SECONDS.labels(flow_name="milestone-2-5-batch-scoring")._value.get() == 7.5
    assert exporter.QUALITY_GATE_LAST_VERDICT.labels(source_table="telco_customers_source")._value.get() == 2.0
    assert exporter.PREDICTIONS_LAST_WRITE_AGE_SECONDS.labels(source_table="telco_customers_source")._value.get() == 99.0


def test_refresh_once_sets_status_minus_one_when_no_run_ever():
    engine = _mock_engine([])
    with (
        patch.object(exporter, "get_client", return_value=_FakeClientContext([])),
        patch.object(exporter, "get_quality_gate_status", return_value={}),
        patch.object(exporter, "get_write_staleness", return_value={}),
    ):
        exporter.refresh_once(engine, flow_name="flow-belum-pernah-jalan")

    assert exporter.FLOW_LAST_STATUS.labels(flow_name="flow-belum-pernah-jalan")._value.get() == -1.0


def test_refresh_once_preserves_last_value_when_flow_query_fails():
    engine = _mock_engine([])
    flow_name = "flow-utk-test-preserve"

    # Set nilai awal via siklus sukses dulu.
    good_run = _make_flow_run(state_type="COMPLETED", duration_seconds=3.0)
    with (
        patch.object(exporter, "get_client", return_value=_FakeClientContext([good_run])),
        patch.object(exporter, "get_quality_gate_status", return_value={}),
        patch.object(exporter, "get_write_staleness", return_value={}),
    ):
        exporter.refresh_once(engine, flow_name=flow_name)
    assert exporter.FLOW_LAST_STATUS.labels(flow_name=flow_name)._value.get() == 1.0

    # Siklus berikutnya: Prefect API gagal -- gauge TIDAK boleh berubah/ke-reset.
    with (
        patch.object(exporter, "get_client", side_effect=RuntimeError("prefect api unreachable")),
        patch.object(exporter, "get_quality_gate_status", return_value={}),
        patch.object(exporter, "get_write_staleness", return_value={}),
    ):
        exporter.refresh_once(engine, flow_name=flow_name)

    assert exporter.FLOW_LAST_STATUS.labels(flow_name=flow_name)._value.get() == 1.0


def test_refresh_once_isolates_failure_per_signal():
    """Kegagalan query quality gate TIDAK boleh menggagalkan update staleness
    di siklus yang sama -- masing-masing try/except independen."""
    run = _make_flow_run(state_type="COMPLETED", duration_seconds=1.0)
    engine = _mock_engine([])

    with (
        patch.object(exporter, "get_client", return_value=_FakeClientContext([run])),
        patch.object(exporter, "get_quality_gate_status", side_effect=RuntimeError("db unreachable")),
        patch.object(exporter, "get_write_staleness", return_value={"telco_customers_source": 42.0}),
    ):
        exporter.refresh_once(engine, flow_name="milestone-2-5-batch-scoring")

    assert exporter.PREDICTIONS_LAST_WRITE_AGE_SECONDS.labels(source_table="telco_customers_source")._value.get() == 42.0
