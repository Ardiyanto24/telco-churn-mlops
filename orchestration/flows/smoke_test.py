"""Flow percobaan minimal -- Milestone 2.1 Checkpoint 4.

Membuktikan platform orchestrator (Prefect Cloud, Managed work pool) bisa
menjalankan job terjadwal. Sengaja TIDAK bergantung ke package
`churn_prediction` -- itu baru relevan Milestone 2.3/2.5 saat DAG batch
sungguhan dibangun. Lihat
milestones/2.1-fondasi-orchestrator-model-registry/decisions.md.
"""

from datetime import datetime, timezone

from prefect import flow, task
from prefect.logging import get_run_logger


@task
def check_in() -> str:
    logger = get_run_logger()
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"Milestone 2.1 smoke test task berjalan pada {timestamp}")
    return timestamp


@flow(name="milestone-2-1-smoke-test")
def smoke_test_flow() -> str:
    logger = get_run_logger()
    timestamp = check_in()
    logger.info(f"Smoke test flow selesai, checked in at {timestamp}")
    return timestamp


if __name__ == "__main__":
    smoke_test_flow()
