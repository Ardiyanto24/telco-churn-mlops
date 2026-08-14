"""Exporter status drift dan kualitas model -- Milestone 3.6. Proses berdiri
sendiri (image lean terpisah, ``infra/docker/drift-exporter.Dockerfile``)
yang mempublikasikan hasil PSI (Tier 1) + KS-test/Chi-square (Tier 2) TERAKHIR
per fitur dari ``drift.drift_check_results`` (ditulis
``scripts/compute_drift.py --mode current``, dipicu event-driven lewat
``.github/workflows/drift-monitoring.yml``) sebagai metrik Prometheus.

TERPISAH dari ``pipeline_health_exporter.py`` (M3.5) -- pilar observability
berbeda (data/model drift vs pipeline health, Bagian 8 dokumen arsitektur),
lihat milestones/3.6-monitoring-drift-kualitas-model/decisions.md
Keputusan #2.

Murni baca hasil JADI (role least-privilege ``drift_reader``, SELECT-only
``drift.drift_check_results`` -- TIDAK bisa lihat data pelanggan sama
sekali) -- komputasi statistik (butuh transform+model, dependency berat)
terjadi di ``scripts/compute_drift.py`` (GitHub Actions), BUKAN di sini.
Pola sama exporter M3.5: compute di pipeline, exporter cuma re-publish
state terakhir.
"""

import logging
import os
import time

import sqlalchemy
from prometheus_client import Gauge, start_http_server

from churn_prediction.drift.metrics import verdict_to_value

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = float(os.environ.get("DRIFT_EXPORTER_POLL_INTERVAL_SECONDS", "30"))
# Nama BUKAN "DRIFT_EXPORTER_PORT" -- Kubernetes inject env var Docker-links
# dari nama Service ("<SERVICE_NAME>_PORT") ke tiap pod di namespace yang
# sama, bentrok dgn nama variabel port sendiri kalau dipakai persis (bug
# nyata ditemukan+diperbaiki di pipeline_health_exporter.py M3.5, lihat
# milestones/3.5-monitoring-infra-pipeline-health/decisions.md).
EXPORTER_HTTP_PORT = int(os.environ.get("EXPORTER_HTTP_PORT", "9101"))

FEATURE_DRIFT_PSI = Gauge(
    "feature_drift_psi",
    "Population Stability Index (Tier 1) run terakhir per fitur",
    ["feature_name"],
)
FEATURE_DRIFT_PVALUE = Gauge(
    "feature_drift_pvalue",
    "p-value uji statistik Tier 2 (KS-test/Chi-square) run terakhir per fitur",
    ["feature_name"],
)
FEATURE_DRIFT_VERDICT = Gauge(
    "feature_drift_verdict",
    "Verdict gabungan run terakhir per fitur: 2=pass, 1=flag, 0=stop",
    ["feature_name"],
)

_LATEST_PER_FEATURE_SQL = sqlalchemy.text(
    """
    SELECT DISTINCT ON (feature_name) feature_name, psi, p_value, verdict
    FROM drift.drift_check_results
    ORDER BY feature_name, computed_at DESC
    """
)


def get_latest_drift_results(engine: sqlalchemy.engine.Engine) -> list[dict]:
    """Hasil drift TERAKHIR per fitur (satu baris per feature_name) --
    dinamis, bukan hardcode daftar fitur."""
    with engine.connect() as conn:
        rows = conn.execute(_LATEST_PER_FEATURE_SQL).fetchall()
    return [
        {"feature_name": row.feature_name, "psi": row.psi, "p_value": row.p_value, "verdict": row.verdict}
        for row in rows
    ]


def refresh_once(engine: sqlalchemy.engine.Engine) -> None:
    """Satu siklus polling -- kegagalan TIDAK mereset gauge, nilai terakhir
    yang berhasil tetap dipertahankan (pola sama pipeline_health_exporter.py
    M3.5/refresh_once M3.4)."""
    try:
        results = get_latest_drift_results(engine)
    except Exception as exc:  # noqa: BLE001 -- boundary polling: jangan crash loop
        logger.warning("Gagal query drift.drift_check_results: %r", exc)
        return

    for result in results:
        feature_name = result["feature_name"]
        FEATURE_DRIFT_PSI.labels(feature_name=feature_name).set(result["psi"])
        FEATURE_DRIFT_PVALUE.labels(feature_name=feature_name).set(result["p_value"])
        FEATURE_DRIFT_VERDICT.labels(feature_name=feature_name).set(verdict_to_value(result["verdict"]))


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = sqlalchemy.create_engine(os.environ["DRIFT_READER_DB_URL"])
    start_http_server(EXPORTER_HTTP_PORT)
    logger.info("drift_exporter listening di port %d, interval poll %.0fs", EXPORTER_HTTP_PORT, POLL_INTERVAL_SECONDS)
    while True:
        refresh_once(engine)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
