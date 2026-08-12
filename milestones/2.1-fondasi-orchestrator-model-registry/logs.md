# Logs — Milestone 2.1: Fondasi Orchestrator dan Model Registry

## Checkpoint 1 — Keputusan tertulis + provisioning kredensial least-privilege

**Mulai:** 2026-08-12.

**Task 1-2:** `CLAUDE.md`/`AGENT.md` diperbarui (syarat "Opsi yang Dipertimbangkan tapi Ditolak" di `decisions.md`), lalu `milestones/2.1-fondasi-orchestrator-model-registry/decisions.md` ditulis — 6 keputusan final dari sesi tanya-jawab (orchestrator Prefect Managed, MLflow direct-access Postgres+Storage, alias `champion`, dst).

**Temuan (sebelum Task 3 dieksekusi):** saat membaca `.env` untuk menyiapkan role Postgres, ditemukan `MLFLOW_TRACKING_URI=http://localhost:5000` dengan komentar "Resmi sejak Milestone 2.1 -- MLflow Tracking Server via Docker" — bertentangan dengan Keputusan #2/#3 `decisions.md` (direct-access, tanpa server, artifact di Supabase Storage). Investigasi:
- `docker ps -a` → container `mlflow-tracking-server` (image `ghcr.io/mlflow/mlflow:latest`) sedang jalan, dibuat `2026-08-12T03:34:47Z`.
- `docker inspect` → command `mlflow server --backend-store-uri sqlite:////mlflow/data/mlruns.db --default-artifact-root /mlflow/data/artifacts`, mount ke folder lokal `mlflow-data/` di repo — SQLite + disk lokal, bukan Postgres/Supabase Storage.
- Tidak ada jejaknya di `decisions.md`/`logs.md` manapun (M1.1-1.6) — kemungkinan eksperimen lokal user di luar sesi ini, mirip pola folder `airflow/logs` kosong yang ditemukan saat eksplorasi awal milestone ini.

**Diagnosis:** konflik nyata antara state lokal dan keputusan yang baru disepakati — berhenti, sampaikan bukti ke user (sesuai `CLAUDE.md` "Cara Memulai Sesi Kerja": jika ada konflik dokumen/implementasi, berhenti dan tunggu arahan), bukan diasumsikan/diteruskan begitu saja.

**Resolusi (dikonfirmasi user via AskUserQuestion):** container Docker adalah eksperimen lama, diabaikan — lanjutkan sesuai `decisions.md` (direct-access Postgres+Storage). Tindakan:
- `docker stop mlflow-tracking-server` — dihentikan (bukan dihapus, tetap reversible kalau diperlukan).
- `.env` `MLFLOW_TRACKING_URI` dikembalikan ke pola M1.5 (`sqlite:///mlruns.db`, sementara) dengan komentar diperbaiki (tidak lagi mengklaim "resmi") — nilai final Postgres akan diisi Task 6 (Checkpoint 2).

**Task 3 (SQL role least-privilege):** SQL disiapkan (`infra/sql/2.1_mlflow_role.sql`, password tidak di-hardcode). Konfirmasi eksplisit diminta ke user sebelum eksekusi (mengubah keamanan database) — dikonfirmasi. Dijalankan lewat `psycopg2` (tidak ada `psql` lokal terpasang) dari `.venv`. Kendala teknis: percobaan pertama gagal (`ENOIDENTIFIER: no tenant identifier provided`) karena pooler Supabase (Supavisor) mensyaratkan username membawa suffix project-ref (`mlflow_registry.<project-ref>`) untuk SEMUA role, bukan cuma role admin — diperbaiki, berhasil di percobaan kedua. **Verifikasi:** role `mlflow_registry` terbukti BISA create/drop table di schema `mlflow`, dan terbukti TIDAK BISA membaca `public.telco_customers_source` (`InsufficientPrivilege`) — scoping least-privilege sesuai desain.

**Task 4:** user provisioning manual (bucket `mlflow-artifacts` + S3 access key di Supabase Storage dashboard, API key Prefect Cloud), nilai diisi ke `.env`. **Temuan:** `PREFECT_API_KEY` awalnya tercopy sekalian perintah CLI (`prefect cloud login -k ...`), bukan cuma key — diperbaiki jadi cuma nilai key-nya. **Verifikasi:** boto3 upload+download+delete objek probe ke bucket `mlflow-artifacts` sukses — koneksi S3-compatible terbukti jalan.

**Temuan keamanan (saat verifikasi S3):** `list_buckets()` menampilkan satu bucket lain dengan nama mencurigakan menyerupai instruksi ke AI agent ("deteksi turn, klasifikasi kebutuhan, pemecahan atomik, verifikasi, cek memory") — dilaporkan ke user sesuai kebijakan anti-prompt-injection (dikutip, tidak ditindaklanjuti), tanpa menyentuh bucket tersebut sama sekali. Tidak memblokir pekerjaan (bucket `mlflow-artifacts` yang dipakai sudah dikonfirmasi terpisah).

**Task 5:** `.env.example` diperbarui dengan variabel resmi M2.1 (placeholder saja).

**Temuan besar kedua (sebelum commit Checkpoint 1):** `git status` menunjukkan repo dalam keadaan **detached HEAD** di `30b00cc` (tip M1.6), sementara branch `main` ternyata 5 commit LEBIH MAJU (`aee1e0c`..`707ef92`, semua bertema "milestone-2.1": MLflow tracking server Docker, config Airflow, registrasi model, alias `production`) — kontradiksi total dengan keputusan sesi ini. Investigasi (`git log`, `git show --stat`) membuktikan commit-commit itu dibuat HARI INI oleh user sendiri (`Ardiyanto24`), belum di-push ke `origin`. Dikonfirmasi ke user: itu eksperimen yang sudah dibatalkan sendiri lewat `git checkout` manual sebelum sesi ini (menjelaskan kenapa HEAD detached). Dikonfirmasi lebih lanjut: `main` di-reset (`git branch -f main 30b00cc`, non-destruktif — 5 commit lama tetap ada di reflog) lalu `git checkout main` untuk melekatkan HEAD kembali ke branch sebelum commit dimulai.

**Interupsi user (aturan commit message):** user menghentikan pekerjaan untuk menambah aturan Conventional Commits + split commit per tipe dalam satu checkpoint. `CLAUDE.md`/`AGENT.md` diperbarui, memory feedback disimpan. Commit Checkpoint 1 yang sudah terlanjur dibuat (`6566ca8`, gabungan feat+docs) diperbaiki: `git reset --soft HEAD~1` (aman, belum di-push) lalu dipecah jadi `1b9656d` (feat: infra SQL + `.env.example`) dan `5fbaab8` (docs: `decisions.md`+`logs.md`).

**Selesai, commit:** `1b9656d` (feat), `5fbaab8` (docs).

## Checkpoint 2 — Registrasi model ke backend MLflow resmi (Postgres + Storage)

**Task 6:** `.env` `MLFLOW_TRACKING_URI` diarahkan ke koneksi `mlflow_registry` (Postgres, direct-access). Variabel S3 dikonsolidasi (`MLFLOW_ARTIFACT_BUCKET=mlflow-artifacts` ditambah). Tidak ada commit (`.env` gitignored).

**Task 7:** `boto3==1.43.69` ditambah, `psycopg2-binary` dipindah dari `[dev]` ke `dependencies` inti (dibutuhkan runtime, bukan cuma test). **Verifikasi:** `pytest tests/ -q` → **136 passed**, tidak ada regresi. Commit: `070def8` (feat).

**Task 8:** `scripts/register_production_model.py` ditulis (memanggil `build_bundle()`/`register_model()` dari `churn_prediction.inference.registry` — TIDAK mendefinisikan ulang logika M1.5) — membuat experiment `churn_prediction_production` dengan `artifact_location=s3://mlflow-artifacts/` secara eksplisit sebelum registrasi (supaya artifact TIDAK jatuh ke default lokal `mlruns/0`). Dijalankan: `churn_prediction_model` versi 1 berhasil teregistrasi.

**Verifikasi (bukti langsung, bukan asumsi):**
- Query `information_schema.tables` → seluruh tabel MLflow (`experiments`, `model_versions`, `registered_models`, `runs`) benar-benar landing di schema `mlflow`, bukan `public`.
- Query `mlflow.model_versions` → baris `('churn_prediction_model', 1, 'None')` terkonfirmasi ada.
- Query `mlflow.experiments` → experiment `churn_prediction_production` (id 1) tercatat dengan `artifact_location='s3://mlflow-artifacts/'`.
- `boto3 list_objects_v2` ke bucket `mlflow-artifacts` → `bundle.joblib` (25.524.954 bytes) dan file model lain (`MLmodel`, `conda.yaml`, `python_model.pkl`, dst.) benar-benar ADA di Storage, bukan cuma metadata di Postgres.

**Selesai, commit:** `070def8` (feat, task 7), `e06eaa9` (feat, task 8), `1b31178` (docs).

## Checkpoint 3 — Konvensi "versi aktif" (alias) + loader baru

**Task 9:** `set_active_alias()`/`load_active_model()` ditambah ke `churn_prediction.inference.registry` (`models:/{name}@{alias}`, lewat `mlflow.tracking.MlflowClient().set_registered_model_alias()`). `ACTIVE_ALIAS = "champion"` ditambah ke `constants.py`. `load_model_by_version()` lama TIDAK diubah/dihapus.

**Task 10:** `scripts/promote_active_alias.py` ditulis (reusable, dipakai lagi saat promosi versi berikutnya/M2.8). Dijalankan: `python scripts/promote_active_alias.py 1` → alias `champion` → versi 1. **Verifikasi:** query `mlflow.registered_model_aliases` → baris `('churn_prediction_model', 'champion', 1)` terkonfirmasi.

**Task 11:** 2 unit test baru ditambah ke `tests/inference/test_registry.py` (pola tracking URI SQLite terisolasi di `tmp_path`, sama seperti test M1.5): (1) round-trip alias vs versi eksplisit menghasilkan prediksi identik, (2) alias reassignment benar-benar version-aware (bukan cache) -- pola sama KK3 M1.5. **Verifikasi:** `pytest tests/inference/test_registry.py -v` → 5 passed. `pytest tests/ -q` → **138 passed** (136 lama + 2 baru), tidak ada regresi.

**Task 12:** `docs/05-model-registry-contract/model-registry-contract.md` ditulis (nama model, backend direct-access, konvensi alias, cara load versi aktif, prosedur promosi/rollback).

**Verifikasi tambahan (round-trip terhadap backend PRODUKSI sungguhan, bukan cuma test terisolasi):** `load_active_model()` vs `load_model_by_version("1")` pada sample data yang sama, dijalankan langsung terhadap `MLFLOW_TRACKING_URI` Postgres+Storage resmi → `churn_probability=0.054475`, `churn_label=0` untuk KEDUANYA, `DataFrame.equals()` True.

**Selesai, commit:** `62da85b` (feat), `4b2eef6` (docs).

## Checkpoint 4 — Prefect Cloud: job terjadwal percobaan

**Task 13:** `prefect==3.8.2` diinstal sebagai optional-dependency `[orchestration]` (bukan dependency inti `churn_prediction`). Login non-interaktif via `PREFECT_API_KEY` (env var, tanpa prompt) → `prefect cloud workspace ls` menemukan workspace `ardi/default` yang sudah ada milik user. Work pool baru `churn-mlops-managed-pool` (tipe `prefect:managed`) dibuat. `PREFECT_API_URL` ditambah ke `.env`/`.env.example` (dibaca dari `~/.prefect/profiles.toml` setelah `workspace set`).

**Task 14:** `orchestration/flows/smoke_test.py` ditulis (flow+task minimal, tidak bergantung `churn_prediction`). **Verifikasi:** dijalankan lokal (`python orchestration/flows/smoke_test.py`) → sukses, run tercatat di Prefect Cloud (state Completed).

**Push ke origin/main:** sebelum deploy, perlu kode ada di GitHub (Prefect Managed menarik kode via `flow.from_source()` dari repo). Konfirmasi eksplisit diminta ke user (aksi push) — dikonfirmasi. `git push origin main` → 9 commit ter-push (`30b00cc..63c977d`).

**Task 15:** `orchestration/deploy_smoke_test.py` ditulis (`flow.from_source(REPO_URL).deploy(...)`, jadwal cron tiap 6 jam -- sekadar bukti, bukan jadwal produksi). Dijalankan → deployment `milestone-2-1-smoke-test/milestone-2-1-smoke-test-deployment` berhasil dibuat. Run manual dipicu (`prefect deployment run`) dan dipoll di background sampai status terminal.

**Verifikasi (bukti log run sungguhan dari Prefect Cloud API, bukan asumsi):**
```
Running 1 deployment pull step(s)
Executing deployment step: git_clone
Deployment step 'git_clone' completed successfully
All deployment steps completed successfully
Beginning flow run 'gifted-hyrax' for flow 'milestone-2-1-smoke-test'
Milestone 2.1 smoke test task berjalan pada 2026-08-12T12:39:51...
Finished in state Completed()
Smoke test flow selesai, checked in at 2026-08-12T12:39:51...
Finished in state Completed()
```
`git_clone` di log membuktikan kode benar-benar ditarik dari GitHub dan dieksekusi di infrastruktur Prefect (Managed work pool) -- BUKAN dijalankan lokal. Flow run status akhir: `COMPLETED`.

**Selesai, commit:** `63c977d` (feat, tasks 13-14), `75f9c0e` (feat, task 15).
