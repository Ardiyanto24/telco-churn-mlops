"""Job agregasi metrik monitoring -- Milestone 3.9. Proses berdiri sendiri
(image Docker lean terpisah, ``infra/docker/metrics-aggregator.Dockerfile``)
yang membaca metrik dari Prometheus (ketiga pilar observability: infra/API
M3.5, drift M3.6, pipeline health M3.5 -- SEMUA sudah terekspos seragam
sebagai gauge/histogram Prometheus lewat exporter existing) dan menulis
snapshot periodik ke tabel generik ``monitoring.metrics_snapshot``
(PostgreSQL) -- realisasi Bagian 8.3 dokumen arsitektur ("PostgreSQL
sebagai sumber utama data monitoring").

Arah data KEBALIKAN dari ``pipeline_health_exporter.py``/``drift_exporter.py``
(yang MENGEKSPOS ``/metrics`` untuk DISCRAPE Prometheus) -- komponen ini
JUSTRU MEMBACA dari Prometheus sebagai client HTTP, lalu menulis ke
PostgreSQL. TIDAK expose port/``/metrics`` sendiri, TIDAK ada Service K8s
(pure background worker). TIDAK mengubah 2 exporter existing sama sekali
(tetap dipakai apa adanya oleh alerting M3.7/M3.8, yang TETAP query
Prometheus langsung -- hanya panel DASHBOARD yang pindah ke PostgreSQL,
lihat milestones/3.9-penyimpanan-data-monitoring-postgresql/decisions.md).

Query PromQL di ``METRIC_SPECS`` SENGAJA disalin PERSIS dari panel
``grafana-dashboard-configmap.yaml`` yang sudah ada (bukan ditulis ulang
berbeda) -- supaya perbandingan "agregasi Postgres vs Prometheus mentah"
(KK1 M3.9) apple-to-apple.
"""

import json
import logging
import os
import time
from typing import Optional

import requests
import sqlalchemy

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get(
    "PROMETHEUS_URL", "http://prometheus.monitoring.svc.cluster.local:9090"
)

# Nama flow Prefect yang dipantau (M2.5/M2.9) -- konsisten
# pipeline_health_exporter.py FLOW_NAME.
_FLOW_NAME = "milestone-2-5-batch-scoring"

# Setiap entri: metric_name OUTPUT (ditulis ke kolom metric_name Postgres),
# promql SUMBER (persis definisi panel dashboard existing), label_keys
# (label Prometheus yang disalin ke kolom `labels` jsonb Postgres -- list
# kosong berarti nilai tunggal tanpa dimensi tambahan).
METRIC_SPECS = [
    # ── Pilar infra/API (M3.5) -- SATU-SATUNYA yang groundtruth-nya murni
    # Prometheus (histogram/counter live), bukan snapshot dari tabel lain.
    {
        "name": "api_request_rate_per_second",
        "promql": 'sum(rate(http_requests_total{job="churn-api",handler="/predict"}[5m])) by (status)',
        "label_keys": ["status"],
    },
    {
        "name": "api_latency_p50_seconds",
        "promql": 'histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{job="churn-api",handler="/predict"}[5m])) by (le))',
        "label_keys": [],
    },
    {
        "name": "api_latency_p95_seconds",
        "promql": 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="churn-api",handler="/predict"}[5m])) by (le))',
        "label_keys": [],
    },
    {
        "name": "api_latency_p99_seconds",
        "promql": 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{job="churn-api",handler="/predict"}[5m])) by (le))',
        "label_keys": [],
    },
    {
        "name": "api_error_rate_percent",
        "promql": (
            '100 * sum(rate(http_requests_total{job="churn-api",handler="/predict",status=~"4xx|5xx"}[5m])) '
            '/ sum(rate(http_requests_total{job="churn-api",handler="/predict"}[5m]))'
        ),
        "label_keys": [],
    },
    # ── Pilar pipeline health (M3.5/M2.4/M2.5) -- groundtruth aslinya
    # Prefect Cloud API (status/durasi flow) atau tabel Postgres lain
    # (gerbang kualitas, staleness), tapi SUDAH seragam sbg gauge Prometheus
    # lewat pipeline_health_exporter.py -- dibaca dari situ, bukan sumber
    # aslinya langsung (Keputusan Desain #3 plan).
    {
        "name": "pipeline_flow_status",
        "promql": f'pipeline_flow_last_status{{flow_name="{_FLOW_NAME}"}}',
        "label_keys": ["flow_name"],
    },
    {
        "name": "pipeline_flow_duration_seconds",
        "promql": f'pipeline_flow_last_duration_seconds{{flow_name="{_FLOW_NAME}"}}',
        "label_keys": ["flow_name"],
    },
    {
        "name": "quality_gate_verdict",
        "promql": "quality_gate_last_verdict",
        "label_keys": ["source_table"],
    },
    {
        "name": "predictions_staleness_seconds",
        "promql": "predictions_last_write_age_seconds",
        "label_keys": ["source_table"],
    },
    # ── Pilar drift (M3.6) -- groundtruth aslinya drift.drift_check_results,
    # sudah seragam sbg gauge Prometheus lewat drift_exporter.py.
    {
        "name": "drift_psi",
        "promql": "feature_drift_psi",
        "label_keys": ["feature_name"],
    },
    {
        "name": "drift_pvalue",
        "promql": "feature_drift_pvalue",
        "label_keys": ["feature_name"],
    },
    {
        "name": "drift_verdict",
        "promql": "feature_drift_verdict",
        "label_keys": ["feature_name"],
    },
]


def query_prometheus(promql: str, prometheus_url: str = PROMETHEUS_URL) -> list[dict]:
    """Jalankan satu query instant PromQL lewat Prometheus HTTP API, return
    list hasil `{"value": float, "labels": {...}}` per series.

    Tidak melempar exception ke pemanggil untuk hasil kosong (query valid
    tapi tidak ada series cocok) -- return list kosong, bukan anomali.
    Exception jaringan/HTTP DIBIARKAN naik ke pemanggil (`refresh_once()`,
    Task 7) yang mengisolasi per metric spec.
    """
    response = requests.get(
        f"{prometheus_url}/api/v1/query",
        params={"query": promql},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query gagal: {payload}")

    results = []
    for series in payload["data"]["result"]:
        metric_labels = series.get("metric", {})
        raw_value = series["value"][1]
        results.append({"value": float(raw_value), "labels": dict(metric_labels)})
    return results


def _filter_label_keys(labels: dict, label_keys: list[str]) -> dict:
    """Sisakan HANYA label yang eksplisit terdaftar di `label_keys` spec --
    Prometheus metric bisa punya label tambahan (mis. `instance`/`job`) yang
    tidak relevan disimpan di kolom `labels` Postgres."""
    return {k: labels[k] for k in label_keys if k in labels}


def write_snapshot_rows(
    engine: sqlalchemy.engine.Engine, metric_name: str, results: list[dict]
) -> int:
    """Tulis satu baris ``monitoring.metrics_snapshot`` per hasil query
    Prometheus (satu per series) -- `computed_at` default `now()` DB side,
    supaya seluruh baris dalam satu siklus dapat timestamp konsisten
    terlepas durasi proses Python.

    Return jumlah baris yang ditulis (0 kalau `results` kosong -- BUKAN
    dianggap error, mis. `pipeline_flow_status` sebelum flow pernah jalan)."""
    if not results:
        return 0
    query = sqlalchemy.text(
        """
        INSERT INTO monitoring.metrics_snapshot (metric_name, value, labels)
        VALUES (:metric_name, :value, CAST(:labels AS jsonb))
        """
    )
    rows = [
        {"metric_name": metric_name, "value": r["value"], "labels": json.dumps(r["labels"])}
        for r in results
    ]
    with engine.begin() as conn:
        conn.execute(query, rows)
    return len(rows)


def refresh_once(
    engine: sqlalchemy.engine.Engine, prometheus_url: str = PROMETHEUS_URL
) -> None:
    """Satu siklus polling penuh -- iterasi seluruh `METRIC_SPECS`, tulis
    snapshot per metrik. Tiap metric spec diisolasi try/except SENDIRI
    (pola sama `pipeline_health_exporter.refresh_once()`/`drift_exporter
    .refresh_once()`) -- kegagalan SATU metrik (mis. Prometheus timeout
    utk satu query) tidak menggagalkan metrik lain di siklus yang sama."""
    for spec in METRIC_SPECS:
        try:
            raw_results = query_prometheus(spec["promql"], prometheus_url)
            filtered = [
                {"value": r["value"], "labels": _filter_label_keys(r["labels"], spec["label_keys"])}
                for r in raw_results
            ]
            written = write_snapshot_rows(engine, spec["name"], filtered)
            logger.info("Menulis %d baris untuk metric_name=%s", written, spec["name"])
        except Exception as exc:  # noqa: BLE001 -- boundary polling: jangan crash loop
            logger.warning("Gagal proses metric spec %r: %r", spec["name"], exc)


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO)
    poll_interval = float(os.environ.get("METRICS_AGGREGATOR_POLL_INTERVAL_SECONDS", "60"))
    engine = sqlalchemy.create_engine(os.environ["MONITORING_METRICS_WRITER_DB_URL"])
    logger.info(
        "metrics_aggregator mulai, interval poll %.0fs, prometheus_url=%s",
        poll_interval,
        PROMETHEUS_URL,
    )
    while True:
        refresh_once(engine)
        time.sleep(poll_interval)


if __name__ == "__main__":
    run_forever()
