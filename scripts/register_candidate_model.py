"""Registrasi versi KANDIDAT UJI ke MLflow Model Registry -- Milestone 2.8.

BEDA dari `register_production_model.py` (M2.1, registrasi resmi produksi):
skrip ini registrasi model+preprocessor YANG SAMA PERSIS (TIDAK training
ulang -- lihat CLAUDE.md), tapi dengan threshold UJI (0.5, bukan 0.6238
produksi) -- pola sama tests/inference/test_registry.py (M1.5). Tujuannya
murni menghasilkan kandidat versi yang genuinely berbeda outputnya (bukan
duplikat identik) untuk menguji mekanisme verifikasi-sebelum-promosi/
promosi/rollback (M2.8) TANPA menyentuh model produksi yang sudah ada.

Alias `challenger` (BUKAN `champion`) -- konvensi dicadangkan eksplisit
Milestone 2.1 untuk "versi kandidat sedang diverifikasi", lihat
docs/05-model-registry-contract/model-registry-contract.md.

Lolos gerbang sanity check (Milestone 2.8 Checkpoint 1) OTOMATIS -- sudah
dipasang di dalam `register_model()`, tidak perlu dipanggil terpisah di sini.
"""

import mlflow

from churn_prediction.inference.constants import ACTIVE_ALIAS, MODEL_NAME
from churn_prediction.inference.registry import build_bundle, register_model, set_active_alias

CANDIDATE_ALIAS = "challenger"
TEST_THRESHOLD = 0.5
EXPERIMENT_NAME = "churn_prediction_production"


def main():
    experiment = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
    if experiment is not None:
        mlflow.set_experiment(EXPERIMENT_NAME)

    bundle = build_bundle(threshold=TEST_THRESHOLD)
    model_info = register_model(bundle)
    version = model_info.registered_model_version

    set_active_alias(version, alias=CANDIDATE_ALIAS)

    print(f"Registered {MODEL_NAME} version {version} (KANDIDAT UJI, threshold={TEST_THRESHOLD})")
    print(f"Alias '{CANDIDATE_ALIAS}' -> version {version}")
    print(f"(alias '{ACTIVE_ALIAS}' TIDAK diubah -- versi produksi tetap aktif)")


if __name__ == "__main__":
    main()
