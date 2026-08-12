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

**Task 3 (SQL role least-privilege):** menyusul, dieksekusi setelah temuan di atas diselesaikan.
