"""Deploy `batch_scoring_flow` ke Prefect Cloud Managed work pool -- Milestone
2.5 Checkpoint 3 Task 11.

SENGAJA TIDAK menyertakan jadwal cron aktif (lihat
milestones/2.5-batch-scoring-dag/decisions.md Keputusan #2) -- data sumber
`telco_customers_source` statis, run berulang pada jadwal nyata akan
menghasilkan prediksi identik tanpa informasi baru sampai generator (Fase 2)
aktif. Deployment ini dibuktikan jalan lewat SATU run manual (`prefect
deployment run`), bukan jadwal aktif.

Kredensial (koneksi Postgres least-privilege, MLflow, S3-compatible)
DISIMPAN sebagai Prefect Secret block -- BUKAN plaintext di job_variables
(prinsip least-privilege/no-hardcoded-secrets CLAUDE.md tetap berlaku
meski disimpan di Prefect Cloud, pihak ketiga).
"""

import os

from prefect import flow
from prefect.blocks.system import Secret

REPO_URL = "https://github.com/Ardiyanto24/telco-churn-mlops.git"
ENTRYPOINT = "orchestration/flows/batch_scoring.py:batch_scoring_flow"
WORK_POOL_NAME = "churn-mlops-managed-pool"
DEPLOYMENT_NAME = "milestone-2-5-batch-scoring-deployment"

SECRET_ENV_VARS = [
    "BATCH_READER_DB_URL",
    "BATCH_WRITER_DB_URL",
    "MLFLOW_TRACKING_URI",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "MLFLOW_S3_ENDPOINT_URL",
    "QUALITY_GATE_DB_URL",
]


def _load_env():
    values = {}
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def _block_slug(var_name: str) -> str:
    return var_name.lower().replace("_", "-")


def _save_secret_blocks(env: dict) -> dict:
    """Simpan tiap kredensial sebagai Prefect Secret block, kembalikan dict
    env-var-name -> template reference (`{{ prefect.blocks.secret.<slug> }}`)."""
    env_refs = {}
    for var_name in SECRET_ENV_VARS:
        value = env[var_name]
        slug = _block_slug(var_name)
        Secret(value=value).save(slug, overwrite=True)
        env_refs[var_name] = f"{{{{ prefect.blocks.secret.{slug} }}}}"
        print(f"Secret block disimpan: {slug}")
    return env_refs


def main():
    env = _load_env()
    env_refs = _save_secret_blocks(env)
    env_refs["MLFLOW_ARTIFACT_BUCKET"] = env["MLFLOW_ARTIFACT_BUCKET"]  # bukan rahasia

    deployment_id = flow.from_source(
        source=REPO_URL,
        entrypoint=ENTRYPOINT,
    ).deploy(
        name=DEPLOYMENT_NAME,
        work_pool_name=WORK_POOL_NAME,
        job_variables={
            "pip_packages": [f"git+{REPO_URL}"],
            "env": env_refs,
        },
        # TIDAK ADA parameter `cron`/`schedule` -- lihat docstring modul ini.
    )
    print(f"Deployed: {deployment_id}")


if __name__ == "__main__":
    main()
