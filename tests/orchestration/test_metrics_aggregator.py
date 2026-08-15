"""Unit test -- Milestone 3.9 Checkpoint 2: metrics_aggregator.

Mock HTTP Prometheus + DB engine -- TIDAK butuh kredensial/cluster
sungguhan. Verifikasi manual terhadap Prometheus+Supabase NYATA dilakukan
terpisah saat implementasi (dicatat di
milestones/3.9-penyimpanan-data-monitoring-postgresql/logs.md)."""

from unittest.mock import MagicMock, patch

import pytest

from orchestration.monitoring import metrics_aggregator as agg


def _mock_prometheus_response(result_series):
    """`result_series`: list of (value_str, metric_labels_dict)."""
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": labels, "value": [1700000000.0, value]}
                for value, labels in result_series
            ],
        },
    }
    return response


def _mock_write_engine():
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    return engine, conn


# ── query_prometheus ─────────────────────────────────────────────────────


def test_query_prometheus_parses_multi_series_with_labels():
    response = _mock_prometheus_response(
        [("0.02", {"feature_name": "tenure"}), ("0.30", {"feature_name": "service_count"})]
    )
    with patch.object(agg.requests, "get", return_value=response) as mock_get:
        results = agg.query_prometheus("feature_drift_psi", "http://prom:9090")

    mock_get.assert_called_once_with(
        "http://prom:9090/api/v1/query", params={"query": "feature_drift_psi"}, timeout=10
    )
    assert results == [
        {"value": 0.02, "labels": {"feature_name": "tenure"}},
        {"value": 0.30, "labels": {"feature_name": "service_count"}},
    ]


def test_query_prometheus_parses_single_value_without_labels():
    response = _mock_prometheus_response([("0.842", {})])
    with patch.object(agg.requests, "get", return_value=response):
        results = agg.query_prometheus("histogram_quantile(0.95, ...)")
    assert results == [{"value": 0.842, "labels": {}}]


def test_query_prometheus_empty_result_returns_empty_list():
    response = _mock_prometheus_response([])
    with patch.object(agg.requests, "get", return_value=response):
        results = agg.query_prometheus("pipeline_flow_last_status{flow_name=\"belum-pernah-ada\"}")
    assert results == []


def test_query_prometheus_raises_on_error_status():
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"status": "error", "error": "bad query"}
    with patch.object(agg.requests, "get", return_value=response):
        with pytest.raises(RuntimeError, match="Prometheus query gagal"):
            agg.query_prometheus("invalid{{{")


# ── _filter_label_keys ───────────────────────────────────────────────────


def test_filter_label_keys_keeps_only_specified_keys():
    labels = {"feature_name": "tenure", "instance": "x:9101", "job": "drift-exporter"}
    assert agg._filter_label_keys(labels, ["feature_name"]) == {"feature_name": "tenure"}


def test_filter_label_keys_empty_spec_returns_empty_dict():
    labels = {"instance": "x:9101"}
    assert agg._filter_label_keys(labels, []) == {}


def test_filter_label_keys_missing_key_silently_omitted():
    assert agg._filter_label_keys({}, ["source_table"]) == {}


# ── write_snapshot_rows ───────────────────────────────────────────────────


def test_write_snapshot_rows_inserts_one_row_per_result():
    engine, conn = _mock_write_engine()
    written = agg.write_snapshot_rows(
        engine,
        "drift_psi",
        [{"value": 0.02, "labels": {"feature_name": "tenure"}}, {"value": 0.30, "labels": {"feature_name": "service_count"}}],
    )
    assert written == 2
    conn.execute.assert_called_once()
    _, call_args = conn.execute.call_args
    rows = conn.execute.call_args[0][1]
    assert len(rows) == 2
    assert rows[0]["metric_name"] == "drift_psi"
    assert rows[0]["value"] == 0.02
    assert '"feature_name": "tenure"' in rows[0]["labels"]


def test_write_snapshot_rows_empty_results_skips_db_call():
    engine, conn = _mock_write_engine()
    written = agg.write_snapshot_rows(engine, "pipeline_flow_status", [])
    assert written == 0
    conn.execute.assert_not_called()


# ── refresh_once ──────────────────────────────────────────────────────────


def test_refresh_once_writes_for_every_metric_spec():
    engine, conn = _mock_write_engine()
    with patch.object(agg, "query_prometheus", return_value=[{"value": 1.0, "labels": {}}]) as mock_query:
        agg.refresh_once(engine, prometheus_url="http://prom:9090")

    assert mock_query.call_count == len(agg.METRIC_SPECS)
    assert conn.execute.call_count == len(agg.METRIC_SPECS)


def test_refresh_once_isolates_failure_per_metric_spec():
    engine, conn = _mock_write_engine()

    def _flaky_query(promql, prometheus_url=agg.PROMETHEUS_URL):
        if promql == "feature_drift_psi":
            raise RuntimeError("prometheus timeout")
        return [{"value": 1.0, "labels": {}}]

    with patch.object(agg, "query_prometheus", side_effect=_flaky_query):
        agg.refresh_once(engine)

    # 12 spec total, 1 gagal (drift_psi) -- 11 sisanya tetap ditulis.
    assert conn.execute.call_count == len(agg.METRIC_SPECS) - 1


def test_refresh_once_no_series_writes_nothing_for_that_spec():
    engine, conn = _mock_write_engine()
    with patch.object(agg, "query_prometheus", return_value=[]):
        agg.refresh_once(engine)
    conn.execute.assert_not_called()
