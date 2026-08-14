"""Exporter status pipeline batch -- Milestone 3.5. Proses berdiri sendiri
(image lean terpisah, ``infra/docker/exporter.Dockerfile``) yang mengubah 3
sinyal pipeline health (``docs/02-implementation-plan/
mlops-03-deployment-observability.md`` baris 113-128) jadi metrik Prometheus:

- status + durasi run terakhir flow Prefect ``milestone-2-5-batch-scoring``
  (M2.5/M2.9, satu flow untuk kedua source_table -- lihat
  ``orchestration/flows/batch_scoring.py`` baris 266).
- verdict gerbang kualitas data terakhir per ``source_table`` (M2.4,
  ``quality.gate_run_history``).
- staleness tulis-balik per ``source_table`` (M2.5/M2.9,
  ``predictions.batch_predictions``).

Murni OBSERVASIONAL dari luar (Prefect REST API + query Postgres langsung
via role least-privilege ``monitoring_reader``, SELECT-only) -- TIDAK
mengubah ``orchestration/flows/batch_scoring.py`` maupun
``src/churn_prediction/quality/*`` sama sekali (Keputusan #8
milestones/3.5-monitoring-infra-pipeline-health/decisions.md).

Kalau satu sinyal gagal diambil (mis. Prefect API/Postgres sesaat tidak
terjangkau), gauge terkait TIDAK di-reset -- nilai terakhir yang berhasil
tetap dipertahankan (perilaku bawaan ``prometheus_client.Gauge``, cukup
dengan TIDAK memanggil ``.set()`` saat exception; pola sama
``_refresh_once`` M3.4 yang mempertahankan model lama saat refresh gagal).
"""

import asyncio
import logging
import os
import time
from typing import Optional

import sqlalchemy
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import FlowFilter, FlowFilterName
from prefect.client.schemas.sorting import FlowRunSort
from prometheus_client import Gauge, start_http_server

logger = logging.getLogger(__name__)

FLOW_NAME = "milestone-2-5-batch-scoring"

# Tidak ada SLA formal (pola sama REFRESH_INTERVAL_SECONDS M3.4) -- 30 detik
# dipilih cukup responsif tanpa membebani Prefect API/Postgres dengan polling
# berlebihan. Bisa diubah tanpa ubah kode (env var).
POLL_INTERVAL_SECONDS = float(os.environ.get("PIPELINE_HEALTH_POLL_INTERVAL_SECONDS", "30"))
EXPORTER_PORT = int(os.environ.get("PIPELINE_HEALTH_EXPORTER_PORT", "9100"))

_VERDICT_TO_VALUE = {"pass": 2.0, "flag": 1.0, "stop": 0.0}

FLOW_LAST_STATUS = Gauge(
    "pipeline_flow_last_status",
    "Status run terakhir: 1=Completed, 0=Failed/Crashed/lainnya, -1=belum pernah ada run",
    ["flow_name"],
)
FLOW_LAST_DURATION_SECONDS = Gauge(
    "pipeline_flow_last_duration_seconds",
    "Durasi run terakhir (detik)",
    ["flow_name"],
)
FLOW_LAST_RUN_TIMESTAMP_SECONDS = Gauge(
    "pipeline_flow_last_run_timestamp_seconds",
    "Unix epoch waktu selesai run terakhir",
    ["flow_name"],
)
QUALITY_GATE_LAST_VERDICT = Gauge(
    "quality_gate_last_verdict",
    "Verdict run gerbang kualitas data terakhir: 2=pass, 1=flag, 0=stop",
    ["source_table"],
)
PREDICTIONS_LAST_WRITE_AGE_SECONDS = Gauge(
    "predictions_last_write_age_seconds",
    "Detik sejak tulis-balik terakhir ke predictions.batch_predictions",
    ["source_table"],
)


async def get_latest_flow_run(flow_name: str = FLOW_NAME) -> Optional[dict]:
    """Ambil run terakhir (berdasar end_time) untuk flow tertentu dari
    Prefect Cloud. Return None kalau belum pernah ada run -- BUKAN exception,
    supaya pemanggil bisa membedakan "belum ada run" dari kegagalan koneksi."""
    async with get_client() as client:
        runs = await client.read_flow_runs(
            flow_filter=FlowFilter(name=FlowFilterName(any_=[flow_name])),
            sort=FlowRunSort.END_TIME_DESC,
            limit=1,
        )
    if not runs:
        return None
    run = runs[0]
    return {
        "state_type": run.state_type.value if run.state_type else None,
        "duration_seconds": run.total_run_time.total_seconds() if run.total_run_time else 0.0,
        "end_time_epoch": run.end_time.timestamp() if run.end_time else None,
    }


def get_quality_gate_status(engine: sqlalchemy.engine.Engine) -> dict:
    """Verdict terakhir per source_table dari quality.gate_run_history --
    dinamis (GROUP BY source_table langsung), bukan hardcode daftar tabel."""
    query = sqlalchemy.text(
        """
        SELECT DISTINCT ON (source_table) source_table, verdict
        FROM quality.gate_run_history
        ORDER BY source_table, run_at DESC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()
    return {row.source_table: row.verdict for row in rows}


def get_write_staleness(engine: sqlalchemy.engine.Engine) -> dict:
    """Detik sejak tulis-balik terakhir per source_table dari
    predictions.batch_predictions -- dinamis, sama pola dengan
    get_quality_gate_status()."""
    query = sqlalchemy.text(
        """
        SELECT source_table, EXTRACT(EPOCH FROM (now() - MAX(predicted_at))) AS age_seconds
        FROM predictions.batch_predictions
        GROUP BY source_table
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()
    return {row.source_table: float(row.age_seconds) for row in rows}


def _flow_status_value(state_type: Optional[str]) -> float:
    if state_type is None:
        return -1.0
    return 1.0 if state_type == "COMPLETED" else 0.0


def refresh_once(engine: sqlalchemy.engine.Engine, flow_name: str = FLOW_NAME) -> None:
    """Satu siklus polling penuh -- dipanggil berkala oleh run_forever()
    (pola sama _refresh_once/_refresh_loop M3.4). Tiap sinyal diisolasi
    try/except sendiri -- kegagalan satu sinyal tidak menggagalkan sinyal
    lain di siklus yang sama."""
    try:
        run = asyncio.run(get_latest_flow_run(flow_name))
    except Exception as exc:  # noqa: BLE001 -- boundary polling: jangan crash loop
        logger.warning("Gagal cek flow run terakhir %r: %r", flow_name, exc)
    else:
        if run is None:
            FLOW_LAST_STATUS.labels(flow_name=flow_name).set(-1.0)
        else:
            FLOW_LAST_STATUS.labels(flow_name=flow_name).set(_flow_status_value(run["state_type"]))
            FLOW_LAST_DURATION_SECONDS.labels(flow_name=flow_name).set(run["duration_seconds"])
            if run["end_time_epoch"] is not None:
                FLOW_LAST_RUN_TIMESTAMP_SECONDS.labels(flow_name=flow_name).set(run["end_time_epoch"])

    try:
        for source_table, verdict in get_quality_gate_status(engine).items():
            QUALITY_GATE_LAST_VERDICT.labels(source_table=source_table).set(
                _VERDICT_TO_VALUE.get(verdict, -1.0)
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal query status gerbang kualitas data: %r", exc)

    try:
        for source_table, age_seconds in get_write_staleness(engine).items():
            PREDICTIONS_LAST_WRITE_AGE_SECONDS.labels(source_table=source_table).set(age_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal query staleness tulis-balik predictions: %r", exc)


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = sqlalchemy.create_engine(os.environ["MONITORING_READER_DB_URL"])
    start_http_server(EXPORTER_PORT)
    logger.info("pipeline_health_exporter listening di port %d, interval poll %.0fs", EXPORTER_PORT, POLL_INTERVAL_SECONDS)
    while True:
        refresh_once(engine)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
