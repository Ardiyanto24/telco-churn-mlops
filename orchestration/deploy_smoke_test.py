"""Deploy `smoke_test_flow` ke Prefect Cloud Managed work pool -- Milestone 2.1
Checkpoint 4 Task 15. Kode flow ditarik langsung dari GitHub repo publik
(bukan build image/container -- prinsip Managed work pool, lihat
milestones/2.1-fondasi-orchestrator-model-registry/decisions.md Keputusan #1).

Jadwal tiap 6 jam sekadar bukti job terjadwal benar-benar jalan (KK M2.1) --
bukan jadwal produksi sungguhan, itu keputusan M2.3/2.5.
"""

from prefect import flow

REPO_URL = "https://github.com/Ardiyanto24/telco-churn-mlops.git"
ENTRYPOINT = "orchestration/flows/smoke_test.py:smoke_test_flow"
WORK_POOL_NAME = "churn-mlops-managed-pool"
DEPLOYMENT_NAME = "milestone-2-1-smoke-test-deployment"
SCHEDULE_CRON = "0 */6 * * *"


def main():
    deployment_id = flow.from_source(
        source=REPO_URL,
        entrypoint=ENTRYPOINT,
    ).deploy(
        name=DEPLOYMENT_NAME,
        work_pool_name=WORK_POOL_NAME,
        cron=SCHEDULE_CRON,
    )
    print(f"Deployed: {deployment_id}")


if __name__ == "__main__":
    main()
