"""Registrasi resmi `model_final.joblib` ke MLflow Model Registry -- Milestone 2.1.

Beda dari registrasi uji Milestone 1.5 (tracking URI lokal sementara), skrip ini
menunjuk ke registry resmi (`MLFLOW_TRACKING_URI` -- direct-access Postgres
Supabase, lihat milestones/2.1-fondasi-orchestrator-model-registry/decisions.md
Keputusan #2) dan artifact store resmi (Supabase Storage S3-compatible,
Keputusan #3). Memakai `build_bundle()`/`register_model()` dari
`churn_prediction.inference.registry` -- TIDAK mendefinisikan ulang logika
loading/registrasi (satu sumber kebenaran, lihat CLAUDE.md).

Dipakai lagi (bukan sekali-jalan) kalau versi model production perlu
diregistrasi ulang di masa depan -- mis. sebelum M2.8 (promosi versi baru).
"""

import os

import mlflow

from churn_prediction.inference.constants import MODEL_NAME
from churn_prediction.inference.registry import build_bundle, register_model

EXPERIMENT_NAME = "churn_prediction_production"
ARTIFACT_LOCATION = f"s3://{os.environ['MLFLOW_ARTIFACT_BUCKET']}/"


def main():
    experiment = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
    if experiment is None:
        mlflow.create_experiment(EXPERIMENT_NAME, artifact_location=ARTIFACT_LOCATION)
    mlflow.set_experiment(EXPERIMENT_NAME)

    bundle = build_bundle()
    model_info = register_model(bundle)

    print(f"Registered {MODEL_NAME} version {model_info.registered_model_version}")
    print(f"Run artifact_uri: {model_info.artifact_path}")


if __name__ == "__main__":
    main()
