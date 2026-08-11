"""Inference service package -- Milestone 1.5. Titik masuk utama untuk Orang #2
(batch DAG) dan Orang #3 (real-time API): satu fungsi publik, `predict()`, yang
membungkus transformasi (`churn_prediction.transform`) dan model (dimuat dari
MLflow registry berdasarkan versi) menjadi satu pemanggilan.

## Instalasi

    pip install -e .          # dari root repo, jalur pengembangan
    pip install <path-repo>   # dari luar konteks pengembangan (KK1) --
                               # menghasilkan distribusi terinstal, bukan
                               # symlink ke source tree

Dependency (`pyproject.toml`) mencakup semua yang dibutuhkan `predict()`
(mlflow-skinny, sqlalchemy, pandera, pydantic, scikit-learn, lightgbm,
xgboost, dst) -- diverifikasi end-to-end dari venv terpisah yang benar-benar
bersih (Milestone 1.5 Checkpoint 5, KK1), TANPA butuh `artifacs/` (artifact
mentah DS) sama sekali -- itu cuma dipakai saat REGISTRASI versi baru
(`registry.build_bundle()`+`register_model()`), bukan saat memanggil `predict()`.

## Kontrak: `predict(df, model_version, tracking_uri=None) -> DataFrame`

Input (`df`): `pandas.DataFrame`, 1+ baris, 19 kolom fitur snake_case --
SKEMA SAMA dengan `churn_prediction.schema.raw_schema.RawDataSchema` (lihat
tabel di `churn_prediction.schema` untuk pemetaan lengkap field-ke-kolom).
Divalidasi DI DALAM `predict()` -- data tidak lolos validasi (kolom
hilang/tipe salah/di luar rentang wajar) menghasilkan
`pandera.errors.SchemaError`/`SchemaErrors` eksplisit SEBELUM model
dipanggil sama sekali, TIDAK PERNAH diam-diam menghasilkan prediksi salah.

Output: `pandas.DataFrame` (urutan baris = urutan input), 4 kolom:

| Kolom | Tipe | Keterangan |
|---|---|---|
| `churn_probability` | float | `model.predict_proba(X)[:, 1]` (kelas positif = churn) |
| `churn_label` | int (0/1) | `churn_probability >= threshold`, threshold TERSIMPAN DI DALAM bundle versi yang dimuat (bukan konstanta global) |
| `model_version` | str | versi model yang benar-benar dipakai (echo dari argumen `model_version`) |
| `predicted_at` | str | timestamp ISO8601 UTC saat prediksi dijalankan -- lineage minimal (CLAUDE.md, Bagian 5.6 dokumen arsitektur) |

Contoh pemanggilan:

    import pandas as pd
    from churn_prediction.inference import predict

    df = pd.DataFrame([{
        "gender": "Male", "senior_citizen": 0, "partner": "Yes", "dependents": "No",
        "tenure": 29, "phone_service": "Yes", "multiple_lines": "No",
        "internet_service": "DSL", "online_security": "Yes", "online_backup": "No",
        "device_protection": "Yes", "tech_support": "Yes", "streaming_tv": "No",
        "streaming_movies": "No", "contract": "One year", "paperless_billing": "Yes",
        "payment_method": "Mailed check", "monthly_charges": 60.10, "total_charges": 1653.85,
    }])
    result = predict(df, model_version="1")
    # result: churn_probability, churn_label, model_version, predicted_at

## MLflow registry -- LOKAL/UJI milik Milestone 1.5, BUKAN registry resmi

`predict()` memuat model dari MLflow Model Registry berdasarkan versi (bukan
path file statis) lewat env var `MLFLOW_TRACKING_URI` (default
`sqlite:///mlruns.db` kalau tidak diset -- lihat `inference.constants`).
Registry ini SENGAJA lokal/sementara, dibangun untuk membuktikan KK Milestone
1.5 sendiri (mekanisme load-by-version bekerja) -- **registrasi resmi "versi
produksi awal" TETAP tanggung jawab Milestone 2.1**
(`docs/02-implementation-plan/mlops-02-pipeline-orchestration.md`), yang akan
menyediakan MLflow server sungguhan dan konvensi versi aktif. Saat itu
terjadi, Orang #2/#3 cukup mengarahkan `MLFLOW_TRACKING_URI` ke server
tersebut -- kontrak `predict()` tidak berubah.

## Registrasi versi baru (bootstrapping, bukan dipakai Orang #2/#3)

    from churn_prediction.inference import registry

    bundle = registry.build_bundle()          # butuh artifacs/ (dev repo)
    registry.register_model(bundle)           # -> versi baru di registry

Bundle membungkus preprocessor (ter-graft dari `preprocessor.joblib` asli,
`churn_prediction.transform.artifact_loader`) + model (`model_final.joblib`)
+ threshold SEBAGAI SATU ARTIFACT per versi (`inference.pyfunc_model.
ChurnPyfuncModel`) -- supaya rollback ke versi model lama otomatis memakai
preprocessor yang kompatibel dengannya, tanpa langkah sinkronisasi manual
(Bagian 5.4 dokumen arsitektur). Lihat `milestones/1.5-inference-service/
decisions.md` untuk keputusan lengkap.
"""

from .predictor import predict

__all__ = ["predict"]
