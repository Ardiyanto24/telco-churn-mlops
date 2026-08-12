# Kontrak Model Registry — MLflow

Disepakati Milestone 2.1 (`milestones/2.1-fondasi-orchestrator-model-registry/decisions.md` Keputusan #2/#3/#5). Rujukan bersama untuk Orang #2 (batch DAG, M2.2-2.8) dan Orang #3 (real-time API, M3.x) — kedua jalur WAJIB memuat model lewat mekanisme yang sama persis (`churn_prediction.inference.registry`), bukan reimplementasi terpisah.

## 1. Nama Model Terdaftar

`churn_prediction_model` (konstanta `churn_prediction.inference.constants.MODEL_NAME`) — satu nama tunggal untuk seluruh sistem, tidak berubah lintas versi.

## 2. Backend Registry: Direct-Access, Bukan Server

`MLFLOW_TRACKING_URI` mengarah langsung ke Postgres Supabase (`postgresql://mlflow_registry.<project-ref>:...`) lewat role least-privilege `mlflow_registry` (scoped ke schema `mlflow` saja) — **tidak ada** proses `mlflow server` yang perlu dihubungi. Setiap consumer (flow Prefect, nanti real-time API) memanggil `mlflow.set_tracking_uri()` langsung dengan URI yang sama.

Artifact model (bundle preprocessor+model+threshold) disimpan di Supabase Storage lewat protokol S3-compatible (`s3://mlflow-artifacts/`, endpoint dari `MLFLOW_S3_ENDPOINT_URL`).

Tidak ada MLflow UI web yang selalu hidup — untuk browsing experiment/model history, jalankan `mlflow ui --backend-store-uri $MLFLOW_TRACKING_URI` secara lokal on-demand.

## 3. Konvensi "Versi Aktif": MLflow Model Registry Alias

"Versi aktif" — versi model yang dipakai batch DAG dan real-time API untuk prediksi produksi saat ini — didefinisikan lewat **MLflow Model Registry Alias**, BUKAN Stage (deprecated di MLflow) dan bukan tag kustom.

| Alias | Makna |
|---|---|
| `champion` | Versi aktif produksi saat ini. Satu-satunya alias yang WAJIB selalu ada dan menunjuk ke versi valid. |
| `challenger` | Dicadangkan untuk Milestone 2.8 (verifikasi versi kandidat sebelum promosi) — belum dipakai sampai M2.8 dikerjakan. |

Nama alias `champion` adalah konstanta (`churn_prediction.inference.constants.ACTIVE_ALIAS`) — jangan hardcode string literal di kode pemanggil.

## 4. Cara Memuat Versi Aktif (Batch & Real-Time)

Gunakan `churn_prediction.inference.registry.load_active_model(alias="champion")` — setara dengan URI MLflow `models:/churn_prediction_model@champion`. **Jangan** hardcode nomor versi untuk jalur produksi normal.

```python
from churn_prediction.inference.registry import load_active_model

model = load_active_model()  # alias default: "champion"
predictions = model.predict(df)
```

Untuk kebutuhan pin ke versi eksplisit (mis. verifikasi/debug, atau perbandingan kandidat vs aktif di M2.8), tetap tersedia `load_model_by_version(version)` — mengambil `models:/churn_prediction_model/<version>`, tidak dihapus oleh mekanisme alias.

## 5. Cara Mempromosikan Versi Baru

1. Registrasikan artifact baru sebagai kandidat versi lewat `churn_prediction.inference.registry.register_model()` (menghasilkan nomor versi baru, TIDAK otomatis jadi aktif).
2. (Milestone 2.8, belum diimplementasikan) Jalankan sanity check + verifikasi-sebelum-promosi terhadap versi kandidat.
3. Pindahkan alias `champion` ke versi baru lewat `churn_prediction.inference.registry.set_active_alias(version, alias="champion")` — atau `python scripts/promote_active_alias.py <version>`.
4. Batch DAG dan real-time API otomatis memakai versi baru pada pemanggilan `load_active_model()` berikutnya, TANPA perlu redeploy/restart (konsisten prinsip rollback = ganti penanda versi, `CLAUDE.md`).

## 6. Rollback

Sama seperti promosi (langkah 3 di atas), tapi `version` diarahkan ke versi sebelumnya. Tidak ada mekanisme rollback terpisah — rollback DAN promosi adalah operasi yang sama persis (pindah alias), sesuai prinsip arsitektur Bagian 5.2.

## 7. Riwayat Versi

| Versi | Sumber | Status |
|---|---|---|
| 1 | `artifacs/model/model_final.joblib` + `artifacs/proprocessor/preprocessor.joblib` (artifact asli Data Scientist, M1.1) | `champion` (aktif) sejak Milestone 2.1 |
