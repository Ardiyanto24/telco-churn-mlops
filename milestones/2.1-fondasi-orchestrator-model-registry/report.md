# Report — Milestone 2.1: Fondasi Orchestrator dan Model Registry

## Ringkasan

Milestone 2.1 selesai — milestone pertama jalur Orang #2 (`mlops-02-pipeline-orchestration.md`). Enam pertanyaan genuinely-terbuka diajukan sebelum plan ditulis (tool orchestrator, deploy MLflow registry, konvensi versi aktif); pilihan awal user (Airflow + Render/Railow) ternyata tidak feasible secara teknis setelah diriset (bukti konkret, bukan asumsi), sehingga diajukan ulang sampai user memilih arah final: **Prefect Cloud (Managed work pool)** untuk orchestrator, **MLflow direct-access ke Postgres Supabase tanpa proses server** untuk registry, **Supabase Storage (S3-compatible)** untuk artifact store, dan **MLflow Model Registry Alias (`champion`)** untuk konvensi versi aktif.

Dua konflik signifikan ditemukan dan diselesaikan selama eksekusi (lihat `logs.md` untuk detail lengkap): state lokal (container Docker MLflow server) yang bertentangan dengan keputusan baru, dan — lebih signifikan — branch `main` yang 5 commit lebih maju berisi eksperimen Milestone 2.1 lain (Airflow + Docker) yang sudah dibatalkan user sebelum sesi ini, ditemukan lewat `git status` menunjukkan detached HEAD. Keduanya diselesaikan dengan konfirmasi eksplisit user, bukan diasumsikan. User juga menambahkan dua aturan proses baru di tengah eksekusi (didokumentasikan di `CLAUDE.md`/`AGENT.md`): `decisions.md` wajib memuat opsi yang ditolak, dan commit message wajib Conventional Commits dengan split per tipe.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Job percobaan sederhana berhasil dijadwalkan dan dijalankan melalui platform orchestrator. | Deployment `milestone-2-1-smoke-test-deployment` dibuat di work pool `churn-mlops-managed-pool` (jadwal cron tiap 6 jam). Run manual (`prefect deployment run`) mencapai status `COMPLETED` — log run dari Prefect Cloud API membuktikan `git_clone` menarik kode dari GitHub dan dieksekusi di infrastruktur Prefect (Managed), bukan lokal. |
| **KK2** | Model Orang #1 berhasil diregistrasi ke MLflow dan dapat dimuat kembali (round-trip) via mekanisme load-by-version dari inference service package. | `churn_prediction_model` versi 1 teregistrasi (bukti: query langsung `mlflow.model_versions` di Postgres, bukan asumsi). Artifact (`bundle.joblib`, 25.5MB) terverifikasi ADA di bucket `mlflow-artifacts` (Supabase Storage) lewat `boto3 list_objects_v2`. Round-trip `load_active_model()` (alias `champion`) vs `load_model_by_version("1")` menghasilkan prediksi **identik** (`churn_probability=0.054475`, `churn_label=0`), diuji terhadap backend produksi sungguhan (bukan cuma test terisolasi). |
| **KK3** | Definisi "versi aktif" terdokumentasi dan dapat dipahami tanpa ambiguitas oleh pihak lain. | `docs/05-model-registry-contract/model-registry-contract.md` ditulis dan dikirim ke user; dikonfirmasi eksplisit lewat `AskUserQuestion` (peran simulasi "Orang #3", pola sama M1.6) — **"Ya, jelas -- KK3 terpenuhi"**. |

`pytest tests/ -q` final: **138 passed** (136 lama tidak regresi + 2 test baru untuk mekanisme alias).

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 6 keputusan, masing-masing dengan section "Opsi yang Dipertimbangkan tapi Ditolak" beserta bukti (riset kelayakan Airflow di Render/Railow, alasan menolak hosting `mlflow server`, alasan menolak Stage/tag kustom, dst.). Enam pertanyaan diajukan ke user sebelum plan ditulis; satu putaran tambahan diperlukan setelah riset membuktikan pilihan awal (Airflow) tidak feasible gratis-permanen.

## Perubahan dari Plan Awal

- **Dua aturan proses baru ditambahkan user di tengah eksekusi** (bukan bagian plan awal, tapi langsung diterapkan retroaktif ke Checkpoint 1 yang baru saja di-commit): (1) `decisions.md` wajib memuat opsi yang ditolak per keputusan — dikodifikasi di `CLAUDE.md`/`AGENT.md` Bagian "2. Kelola keputusan teknis"; (2) commit message wajib format Conventional Commits, dipecah per tipe kalau checkpoint mencakup lebih dari satu tipe — dikodifikasi di Bagian "3. Implementasikan per checkpoint". Commit Checkpoint 1 yang sudah terlanjur dibuat gabungan (`6566ca8`) diperbaiki via `git reset --soft` (lokal, belum di-push, aman) jadi dua commit terpisah.
- **Dua konflik state tak terduga ditemukan dan diselesaikan** (tidak ada di plan awal, murni temuan eksekusi):
  1. `.env` mengarah ke container Docker MLflow server (SQLite+disk lokal) dengan komentar palsu "Resmi sejak Milestone 2.1" — dikonfirmasi user sebagai eksperimen lama, container dihentikan (`docker stop`, bukan dihapus).
  2. Branch `main` 5 commit lebih maju (`aee1e0c`..`707ef92`) berisi eksperimen Airflow+Docker yang sudah dibatalkan user via `git checkout` manual sebelum sesi ini — dikonfirmasi user, `main` di-reset ke commit sebelum eksperimen itu (`git branch -f main 30b00cc`, non-destruktif, tetap ada di reflog).
- **`psycopg2-binary` dipindah dari `[dev]` ke dependencies inti** — sesuai antisipasi di plan ("verifikasi eksplisit, jangan diasumsikan"), terbukti memang perlu karena registry resmi dipanggil di runtime (bukan cuma test).
- **`prefect` ditambahkan sebagai optional-dependency `[orchestration]`**, bukan dependency inti `churn_prediction` — detail teknis yang tidak eksplisit di plan awal, tapi konsisten prinsip "consumer lain (real-time API M3.x) tidak semua butuh Prefect terpasang".
- Selebihnya, seluruh 5 checkpoint dan 19 task dieksekusi sesuai urutan yang direncanakan.

## Keterbatasan dan Item Terbuka

- **Jadwal cron flow smoke-test (tiap 6 jam) bukan jadwal produksi sungguhan** — sekadar bukti KK1, akan digantikan jadwal nyata saat M2.3 (refresh feature store)/M2.5 (batch scoring DAG) dirancang berdasarkan karakteristik beban sungguhan.
- **Kuota Prefect Managed (10 jam compute/bulan, tier gratis) belum diuji dengan beban nyata** — baru diuji dengan flow smoke-test minimal. Perlu dipantau ulang saat M2.3/2.5 menambah beban kerja sungguhan (dicatat sebagai follow-up, bukan blocker sekarang).
- **`docs/keputusan-tertunda.md` KT-4 (kolom `customer_key`) dan KT-3 (versi xgboost/lightgbm) tidak terpengaruh milestone ini** — tetap terbuka, tidak relevan untuk M2.1.
- **`.env`/kredensial baru** (`mlflow_registry` role, S3 access key, Prefect API key) sepenuhnya lokal di mesin user — belum ada mekanisme secrets management terpusat untuk CI/CD (relevan M2.7).

## Follow-up

- Milestone 2.2 (Klasifikasi Fitur ke Desain Feature Store) siap dimulai — bergantung pada `docs/03-notebook-audit/notebook-audit.md` (sudah ada) dan konvensi versi aktif M2.1 (`docs/05-model-registry-contract/`, sudah tersedia).
- Saat M2.3/M2.5 dirancang, evaluasi ulang kecukupan kuota compute Prefect Managed berdasarkan durasi job sungguhan.
- Ditemukan (bukan diselesaikan) selama verifikasi S3: satu bucket lain di Supabase Storage dengan nama mencurigakan menyerupai instruksi ke AI agent — dilaporkan ke user, tidak ditindaklanjuti/disentuh sesuai kebijakan anti-prompt-injection. User belum memberi klarifikasi asal bucket tersebut.
