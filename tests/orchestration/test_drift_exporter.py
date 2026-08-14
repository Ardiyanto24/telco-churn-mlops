"""Unit test -- Milestone 3.6 Checkpoint 4: exporter drift.

Mock DB engine/koneksi -- TIDAK butuh kredensial sungguhan. Verifikasi
manual terhadap Supabase NYATA sudah dilakukan terpisah saat implementasi
(dicatat di milestones/3.6-monitoring-drift-kualitas-model/logs.md)."""

from unittest.mock import MagicMock, patch

from orchestration.monitoring import drift_exporter as exporter


def _mock_engine(rows):
    engine = MagicMock()
    conn = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    conn.execute.return_value = result
    engine.connect.return_value.__enter__.return_value = conn
    return engine


def _row(feature_name, psi, p_value, verdict):
    row = MagicMock()
    row.feature_name = feature_name
    row.psi = psi
    row.p_value = p_value
    row.verdict = verdict
    return row


def test_get_latest_drift_results_maps_rows_to_dicts():
    engine = _mock_engine([_row("tenure", 0.02, 0.8, "pass")])
    results = exporter.get_latest_drift_results(engine)
    assert results == [{"feature_name": "tenure", "psi": 0.02, "p_value": 0.8, "verdict": "pass"}]


def test_refresh_once_sets_gauges_for_each_feature():
    engine = _mock_engine(
        [
            _row("tenure", 0.02, 0.8, "pass"),
            _row("service_count", 0.30, 0.001, "stop"),
        ]
    )
    exporter.refresh_once(engine)

    assert exporter.FEATURE_DRIFT_PSI.labels(feature_name="tenure")._value.get() == 0.02
    assert exporter.FEATURE_DRIFT_PVALUE.labels(feature_name="tenure")._value.get() == 0.8
    assert exporter.FEATURE_DRIFT_VERDICT.labels(feature_name="tenure")._value.get() == 2

    assert exporter.FEATURE_DRIFT_PSI.labels(feature_name="service_count")._value.get() == 0.30
    assert exporter.FEATURE_DRIFT_VERDICT.labels(feature_name="service_count")._value.get() == 0


def test_refresh_once_handles_flag_verdict():
    engine = _mock_engine([_row("monthly_charges", 0.15, 0.03, "flag")])
    exporter.refresh_once(engine)
    assert exporter.FEATURE_DRIFT_VERDICT.labels(feature_name="monthly_charges")._value.get() == 1


def test_refresh_once_empty_table_does_not_crash():
    engine = _mock_engine([])
    exporter.refresh_once(engine)  # no exception


def test_refresh_once_preserves_last_value_when_query_fails():
    feature_name = "fitur-utk-test-preserve"
    good_engine = _mock_engine([_row(feature_name, 0.05, 0.5, "pass")])
    exporter.refresh_once(good_engine)
    assert exporter.FEATURE_DRIFT_PSI.labels(feature_name=feature_name)._value.get() == 0.05

    with patch.object(exporter, "get_latest_drift_results", side_effect=RuntimeError("db unreachable")):
        exporter.refresh_once(MagicMock())

    # gauge TIDAK berubah/ke-reset meski query gagal di siklus berikutnya.
    assert exporter.FEATURE_DRIFT_PSI.labels(feature_name=feature_name)._value.get() == 0.05
