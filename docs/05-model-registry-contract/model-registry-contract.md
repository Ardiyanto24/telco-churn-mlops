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
| `challenger` | Versi kandidat yang sedang/terakhir diverifikasi (Milestone 2.8) — TIDAK menunjukkan versi itu sudah/akan jadi produksi, cuma penanda "kandidat teregistrasi terakhir". Bisa menunjuk versi yang sama dengan `champion` (setelah promosi) atau versi lain (kandidat baru belum dipromosikan). |

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

Prosedur formal (Milestone 2.8) — siapa berwenang: operator/pemilik registry (Orang #2), manual, tidak ada RBAC formal (proyek solo, sesuai skala Bagian 9 dokumen arsitektur — "Yang Sengaja Berada di Luar Cakupan").

1. Registrasikan artifact sebagai kandidat versi lewat `churn_prediction.inference.registry.register_model()` (menghasilkan nomor versi baru, TIDAK otomatis jadi aktif). **Sanity check** (Milestone 2.8 — `churn_prediction.inference.artifact_validation.sanity_check_bundle()`) berjalan OTOMATIS di dalam `register_model()` — artifact yang gagal (exception, NaN, output di luar kontrak) TIDAK PERNAH sampai ter-log/registrasi. Tag kandidat dengan alias `challenger` lewat `set_active_alias(version, alias="challenger")` — atau `python scripts/register_candidate_model.py` (varian uji, lihat Bagian 7).
2. Jalankan **verifikasi-sebelum-promosi** (`python scripts/verify_before_promotion.py`) — membandingkan kandidat (`challenger`) vs versi aktif (`champion`) pada sampel data production REAL. Wajib: tidak ada exception/NaN pada kandidat. Verdict `pass`/`flag` (delta churn_rate vs ambang provisional) dicetak — TIDAK auto-blocking, cuma masukan untuk keputusan manual berikutnya.
3. **Tinjau verdict secara sadar** (operator) — putuskan lanjut promosi atau tidak berdasarkan angka Langkah 2, bukan otomatis.
4. Pindahkan alias `champion` ke versi kandidat lewat `churn_prediction.inference.registry.set_active_alias(version, alias="champion")` — atau `python scripts/promote_active_alias.py <version> champion`.
5. Batch DAG dan real-time API otomatis memakai versi baru pada pemanggilan `load_active_model()` berikutnya, TANPA perlu redeploy/restart/ubah kode (konsisten prinsip rollback = ganti penanda versi, `CLAUDE.md`) — diverifikasi sungguhan Milestone 2.8 (`batch_scoring_flow()` run nyata, lihat `milestones/2.8-validasi-artifact-promosi-rollback/logs.md`).

## 6. Rollback

Sama seperti promosi Langkah 4 di atas, tapi `version` diarahkan ke versi sebelumnya (mis. `python scripts/promote_active_alias.py 1 champion`). Tidak ada mekanisme rollback terpisah — rollback DAN promosi adalah operasi yang sama persis (pindah alias), sesuai prinsip arsitektur Bagian 5.2. Langkah 1-3 (sanity check, verifikasi-sebelum-promosi) TIDAK relevan untuk rollback — versi yang di-rollback SUDAH pernah lolos gerbang itu saat pertama kali dipromosikan.

Diverifikasi sungguhan Milestone 2.8: promosi ke versi kandidat (threshold uji 0.5) → run DAG nyata → `predictions.batch_predictions.model_version` berubah otomatis → rollback ke versi 1 → run DAG lagi → `model_version` kembali seperti semula. Kecepatan: hitungan detik (`set_active_alias()` + run DAG berikutnya), jauh lebih cepat dari hipotesis redeploy penuh.

## 7. Riwayat Versi

| Versi | Sumber | Status |
|---|---|---|
| 1 | `artifacs/model/model_final.joblib` + `artifacs/proprocessor/preprocessor.joblib` (artifact asli Data Scientist, M1.1), threshold 0.6238 (produksi) | `champion` (aktif) sejak Milestone 2.1 |
| 2 | Model+preprocessor SAMA seperti versi 1 (TIDAK training ulang), threshold 0.5 (UJI, `scripts/register_candidate_model.py`) | `challenger` — kandidat uji Milestone 2.8 untuk memverifikasi mekanisme promosi/rollback/verifikasi-sebelum-promosi. Sempat jadi `champion` sesaat (uji coba terkontrol promosi), di-rollback ke versi 1. **BUKAN rekomendasi produksi** — threshold 0.5 murni artifisial untuk pengujian. |
