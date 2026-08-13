# Decisions — Milestone 3.1: Containerization dan Environment Konsisten

## Konteks

Milestone pertama jalur Orang #3 (`docs/02-implementation-plan/mlops-03-deployment-observability.md`) — tidak ada precedent Docker/container apa pun di proyek ini sebelumnya. Membungkus `churn_prediction.inference` (M1.5) ke Docker container, menjaga environment (Python + seluruh dependency ML) identik dengan yang dikunci `pyproject.toml` (M1.2), dan membuktikan model dapat dimuat dari MLflow registry (alias `champion`) serta menghasilkan prediksi identik dengan run langsung di host.

Tidak ada keputusan yang memerlukan `AskUserQuestion` untuk milestone ini — seluruh 6 keputusan di bawah forced/derived oleh precedent (CI `test.yml`/`batch-scoring.yml`) atau prinsip arsitektur yang sudah final (rollback via alias registry, Bagian 5.1/5.2), bukan pilihan desain bebas. Tetap didokumentasikan lengkap dengan alternatif yang ditolak, konsisten format wajib sejak M2.1.

## Keputusan Teknis

### 1. Base image: `python:3.13-slim`

**Keputusan:** `FROM python:3.13-slim` (`Dockerfile` baris 5).

**Kenapa:** Forced by precedent — `test.yml`/`batch-scoring.yml` sudah pin `python-version: "3.13"` dan terbukti sukses memuat `lightgbm==4.7.0`/`xgboost==3.4.0` di linux (GitHub Actions, sejak M2.7). Memakai versi yang sama persis meniadakan risiko baru yang belum pernah terbukti.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- `python:3.12-slim` — memenuhi floor `requires-python = ">=3.12"`, tapi DITOLAK: tidak match versi yang sudah terbukti sukses di CI, menambah kombinasi Python×dependency baru yang belum pernah diuji tanpa manfaat jelas.
- `python:3.13` (non-slim) — DITOLAK: image jauh lebih besar tanpa manfaat, seluruh dependency ML (`pandas`/`numpy`/`scikit-learn`/`lightgbm`/`xgboost`) tersedia manylinux wheel prebuilt, tidak butuh compiler/toolchain yang cuma ada di image penuh.

### 2. `apt-get install -y --no-install-recommends libgomp1` eksplisit, sebelum `pip install`

**Keputusan:** Baris eksplisit di `Dockerfile` (baris 11-13) menginstal `libgomp1` dari `apt` SEBELUM menginstal dependency Python.

**Kenapa:** Forced by KD-1 (`docs/keterbatasan-diterima.md`) — wheel `lightgbm` tidak membundel `libgomp.so.1`, dan base image `slim` tidak menjamin lib ini ter-install (beda dari `ubuntu-latest` VM penuh yang selama ini "kebetulan" aman — dikonfirmasi tidak ada baris `apt-get install libgomp1` eksplisit di manapun CI existing). Diinstal eksplisit, dan risikonya DIBUKTIKAN nyata di image ini sendiri (lihat `logs.md` Checkpoint 1) — bukan diasumsikan dari teori.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- Mengandalkan base image yang mungkin sudah punya `libgomp1` secara tidak sengaja (mis. pakai `python:3.13` non-slim) — DITOLAK: tidak terverifikasi eksplisit, rawan berubah kalau base image upstream update, dan tetap butuh instalasi eksplisit yang lebih aman/reproducible untuk didokumentasikan sebagai bukti (bukan tebakan).

### 3. Model TIDAK dibake ke image — dimuat runtime dari MLflow registry

**Keputusan:** `Dockerfile` hanya `COPY` `pyproject.toml`, `src/`, `scripts/` — TIDAK `COPY` `artifacs/`. `.dockerignore` eksplisit mengecualikan `artifacs/` (dan `.env`, `.git`, `mlruns/`, `mlflow-data/`, `tests/`, `notebook/`, `docs/`, `milestones/`, `build/`, `airflow/`, `infra/`). Model dimuat lewat `predict_active()`/`load_active_model()` saat container RUN (kredensial via env var saat `docker run --env-file .env`, bukan build time).

**Kenapa:** Forced by prinsip rollback-via-alias registry (Bagian 5.2 arsitektur, dikonfirmasi masih berlaku dari `milestones/2.1-.../decisions.md`) — kalau model dibake ke image, rollback butuh rebuild+redeploy container, kontradiksi langsung dengan janji "rollback cepat tanpa redeploy" yang jadi tujuan eksplisit M3.4.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- Bake `artifacs/model/model_final.joblib`+`preprocessor.joblib` langsung ke image (image "self-contained", tidak butuh network saat start) — DITOLAK: melanggar prinsip rollback-via-registry secara langsung, dan `artifacs/` memang sengaja gitignored/tidak pernah jadi bagian distribusi resmi sejak M1.5.

### 4. Image hanya dependency inti `churn_prediction` (`pip install .`)

**Keputusan:** `pip install --no-cache-dir .` (dependency inti `pyproject.toml` saja) — BUKAN `.[dev]` atau `.[orchestration]`.

**Kenapa:** Image ini untuk inference runtime, bukan menjalankan test suite (`pytest`) atau flow Prefect (`prefect`) di dalamnya — kedua hal itu tetap dijalankan CI/GitHub Actions terpisah (M2.7) atau nanti API server (M3.2) dengan dependency footprint sendiri.

**Opsi yang Dipertimbangkan tapi Ditolak:** tidak ada alternatif dipertimbangkan karena forced by tujuan image (minimal runtime footprint) — extras `[dev]`/`[orchestration]` secara eksplisit didesain "opt-in" sejak M2.1 Keputusan #1, konsisten menyisakannya opsional di sini juga.

### 5. Push ke container registry (GHCR/Docker Hub) di luar cakupan M3.1

**Keputusan:** Milestone ini berhenti di build+run **lokal**. Tidak ada `docker push` ke registry manapun.

**Kenapa:** KK1/KK2 sumber (`mlops-03-deployment-observability.md` Milestone 3.1) hanya minta "container berhasil di-build dan dijalankan" — tidak menyebut publish/registry sama sekali. Push+publish adalah kebutuhan M3.3 (Deployment ke Kubernetes), yang baru butuh image accessible dari cluster.

**Opsi yang Dipertimbangkan tapi Ditolak:** push preventif ke GHCR sekarang (supaya M3.3 tidak perlu mikir ulang) — DITOLAK: menambah keputusan (pilihan registry, autentikasi CI) yang dokumen arsitektur sengaja serahkan ke pemilik pekerjaan terkait pada waktunya (Bagian 10) — dikerjakan sekarang berarti menebak kebutuhan M3.3 sebelum scope-nya digali eksplisit.

### 6. Verifikasi parity: sampel real `telco_customers_source` (limit 1000) via `BATCH_READER_DB_URL`, host vs container

**Keputusan:** `scripts/container_smoke_test.py` fetch `limit=1000` baris dari `telco_customers_source` (pola sama M1.5 KK2/M2.8), jalankan `predict_active()` di host DAN di container pada sampel yang SAMA, bandingkan output persis.

**Kenapa:** Konsisten preferensi proyek ini memakai data real untuk parity check (bukan fixture sintetis) — precedent M1.5 KK2, M2.5, M2.7, M2.8. Yang dibuktikan di sini adalah **environment parity** (versi library identik → angka identik), bukan korektnes model (itu sudah KK2 M1.5, tertutup) — jadi cukup host vs container pada sampel yang sama, TIDAK perlu skala penuh 594rb baris ala KD-1 M2.5 (itu soal beban infra Prefect Managed, risiko berbeda sama sekali).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- Fixture sintetis hardcoded (tanpa DB) — DITOLAK: menyimpang dari preferensi konsisten proyek ini pakai data real untuk parity check, padahal kredensial (`BATCH_READER_DB_URL`) sudah tersedia tanpa biaya tambahan.
- Bandingkan ke ground-truth raw artifact (`model_final.joblib` dimuat langsung tanpa MLflow) ala KK2 M1.5 — DITOLAK: itu sudah dibuktikan tertutup di M1.5, mengulanginya di sini cuma menduplikasi bukti tanpa menambah informasi soal risiko YANG SPESIFIK milestone ini (environment container, bukan korektnes bundle).

## Catatan: Temuan Tak Terduga Selama Implementasi

- **Image cukup besar (1.63GB)** — `xgboost==3.4.0` menarik `nvidia_nccl_cu13` (~252MB) sebagai dependency transitif meski model dijalankan CPU-only (tidak ada GPU di image ini). Tidak ditemukan flag pip untuk mengecualikan extra ini tanpa mengubah cara instalasi (di luar cakupan `pyproject.toml` M1.2 yang sudah mengunci `xgboost==3.4.0` tanpa modifier). TIDAK diperbaiki di milestone ini — bukan kriteria keberhasilan M3.1 manapun (tidak ada target ukuran image), dicatat sebagai observasi untuk dipertimbangkan ulang kalau ukuran image jadi masalah nyata di M3.3 (mis. waktu pull image di cluster).
- **`churn_probability` host vs container TIDAK bitwise-identik** (`np.array_equal` False) tapi **allclose** (`rtol=1e-6`) True dengan diff maksimum ~5.5e-17 — level floating-point rounding noise (kemungkinan urutan operasi BLAS/threading berbeda antara Windows host dan Linux container, walau versi library sama persis). Ini SESUAI ekspektasi KK2 sumber ("output identik") yang tidak mensyaratkan kesamaan bit-per-bit, konsisten definisi parity yang sudah dipakai KK2 M1.5 (`np.allclose(rtol=1e-6)`).
