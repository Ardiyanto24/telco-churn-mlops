# Decisions — Milestone 2.5: Batch Scoring DAG

## Klarifikasi Sebelum Plan Disusun

Dua keputusan dikonfirmasi user sebelum plan ditulis (menjawab celah eksplisit dokumen arsitektur Bagian 10 -- "Frekuensi batch scoring... | Orang #2"):
1. **Skema tabel hasil prediksi:** append-only (insert per run) vs upsert per pelanggan. User memilih **append-only**.
2. **Skala + jadwal:** bangun skala penuh dengan jadwal rutin aktif vs bangun skala penuh tapi verifikasi lewat run terkontrol/manual dulu. User memilih **skala penuh, verifikasi terkontrol/manual, TANPA jadwal rutin aktif**.

Selama eksekusi, tiga temuan signifikan muncul yang butuh keputusan tambahan (lihat Keputusan #5-7).

## Keputusan Teknis

### 1. Tabel hasil prediksi: append-only, `predictions.batch_predictions`

**Keputusan:** Skema baru schema `predictions`, tabel `batch_predictions` (`customer_id`, `churn_probability`, `churn_label`, `model_name`, `model_version`, `model_alias`, `source_table`, `predicted_at`, `batch_run_id`, `flow_run_id`). Role least-privilege baru: `batch_reader` (SELECT-only `telco_customers_source`), `batch_writer` (SELECT+INSERT `batch_predictions` saja, tanpa UPDATE/DELETE — append-only, pola sama `quality_gate` M2.4).

**Kenapa:** Dikonfirmasi user, konsisten pola SCD Type 2 yang sudah dipakai proyek ini di berbagai tempat (KT-2 M1.6, `quality.gate_run_history` M2.4). "Prediksi terkini" per pelanggan didapat lewat query `DISTINCT ON` saat dibaca, bukan disimpan sebagai state terpisah — menghindari kompleksitas upsert dan menyediakan riwayat penuh untuk lineage/audit (KK4 milestone ini eksplisit minta penelusuran balik).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Upsert (1 baris per pelanggan)** — DITOLAK user: kehilangan riwayat historis kecuali dibuat tabel log terpisah (duplikasi konsep), menyimpang dari pola append-only yang sudah konsisten dipakai proyek ini.

### 2. Skala penuh, verifikasi terkontrol/manual, TANPA jadwal rutin aktif

**Keputusan:** DAG dibangun dan dibuktikan mampu memproses SELURUH 594.194 baris `telco_customers_source` (bukan sampel kecil sebagai proxy). Deployment Prefect dibuat, TAPI TIDAK diberi jadwal cron aktif — dibuktikan jalan lewat trigger manual (`prefect deployment run`), bukan berjalan otomatis berulang.

**Kenapa:** Dikonfirmasi user. `telco_customers_source` statis (1 event loading, terverifikasi M2.4) — run berjadwal rutin sekarang akan menghasilkan prediksi identik berulang tanpa informasi baru, pemborosan compute/storage sampai generator (Fase 2 KT-1) aktif dan data harian asli tersedia.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Jadwalkan rutin sekarang juga (mis. harian)** — DITOLAK user, alasan di atas.

### 3. `predict_active()` baru di `predictor.py` — alias, bukan versi eksplisit

**Keputusan:** `predictor.py` mendapat fungsi baru `predict_active(df, alias="champion")` yang memanggil `registry.load_active_model()` (M2.1) — pelengkap `predict(df, model_version)` (M1.5) yang butuh versi eksplisit. Kolom `model_version` di hasil `predict_active()` berisi **nomor versi KONKRET** (`registry.resolve_alias_version()`, fungsi baru), BUKAN nama alias — karena alias mutable (bisa berpindah versi lewat promosi/rollback M2.8), sementara lineage butuh menunjuk versi pasti yang benar-benar menghasilkan prediksi itu.

**Kenapa:** Ditemukan sebelum plan ditulis: `predict()` M1.5 tidak kompatibel langsung dengan mekanisme alias M2.1 (mensyaratkan versi eksplisit). DAG batch (dan nanti real-time API M3.x) perlu memuat "versi aktif" tanpa hardcode nomor versi — `predict_active()` mengisi gap ini tanpa mengubah kontrak `predict()` yang sudah ada dan teruji (satu sumber kebenaran, perluasan bukan reimplementasi).

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **DAG resolve versi aktif sendiri lalu panggil `predict()` biasa** — tidak dipertimbangkan serius: memindahkan logika resolusi alias ke luar package `inference` melanggar "satu sumber kebenaran" (logika loading harus di satu tempat, dipakai bersama batch dan real-time nanti).
- **Kolom `model_version` diisi nama alias (`"champion"`)** — DITOLAK secara teknis (bukan preferensi): alias mutable, tidak memenuhi kebutuhan lineage KK4 yang butuh menunjuk versi PASTI.

### 4. Sentralisasi `RAW_PASCAL_TO_SNAKE` ke `schema/column_mapping.py`

**Keputusan:** Mapping kolom PascalCase→snake_case (sebelumnya terduplikasi identik di 3 file test) dipindah ke `src/churn_prediction/schema/column_mapping.py` — satu sumber kebenaran, DAG jadi konsumen ke-4 tanpa duplikasi baru.

**Kenapa:** Ditemukan sebelum plan ditulis — DAG genuinely butuh mapping ini (titik baca data `telco_customers_source`, pola normalisasi wajib per M1.6 Keputusan #1). Menambah salinan ke-4 di `orchestration/` akan memperbesar risiko drift diam-diam antar salinan yang sudah ada.

**Opsi yang Dipertimbangkan tapi Ditolak:** Duplikasi mapping sekali lagi di `orchestration/flows/batch_scoring.py` — tidak dipertimbangkan serius, bertentangan langsung prinsip satu sumber kebenaran.

### 5. Row Level Security (RLS) Supabase butuh policy eksplisit, bukan cuma GRANT

**Keputusan:** `telco_customers_source` punya RLS aktif tanpa policy apa pun (default Supabase table editor) — `GRANT SELECT` ke `batch_reader` TIDAK CUKUP, RLS tanpa policy menolak semua baris untuk role non-owner. Ditambahkan policy eksplisit `batch_reader_select FOR SELECT TO batch_reader USING (true)`.

**Kenapa:** Ditemukan saat verifikasi Checkpoint 1 — `batch_reader` awalnya `SELECT count(*)` mengembalikan 0 meski GRANT berhasil, padahal tabel berisi 594.194 baris. Root cause: Postgres RLS semantics (aktif+0 policy = deny-all untuk non-owner). `infra/sql/2.5_batch_scoring_roles.sql` diperbarui mencantumkan policy ini eksplisit, bukan cuma di database secara diam-diam.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan — ini forced by cara Postgres RLS bekerja, bukan pilihan desain. (Catatan untuk milestone mendatang: kalau ada tabel BARU dengan RLS aktif yang perlu dibaca role least-privilege, policy eksplisit WAJIB dicek, jangan asumsikan GRANT saja cukup.)

### 6. Bug lintas-platform path artifact MLflow (Windows→Linux) — diperbaiki, bukan diterima sebagai keterbatasan

**Keputusan:** `register_model()` memakai `bundle_path.as_posix()` (bukan `str(bundle_path)`) saat `log_model(artifacts={...})`. Artifact versi 1 yang sudah teregistrasi diperbaiki langsung di Supabase Storage (MLmodel manifest).

**Kenapa:** Ditemukan saat verifikasi Managed (Checkpoint 3) — model gagal dimuat di container Linux dengan `FileNotFoundError` path tercampur separator Windows+Unix. Root cause: bug upstream MLflow yang sudah diketahui ([mlflow/mlflow#11862](https://github.com/mlflow/mlflow/issues/11862)) — model yang di-log dari Windows menyimpan path relatif artifact apa adanya (termasuk backslash) ke manifest, tidak portable ke Linux. INI DIPERBAIKI (bukan masuk `docs/keterbatasan-diterima.md`) karena ada mitigasi konkret yang bisa diterapkan (`.as_posix()`), beda dari Keputusan #7 yang genuinely tidak ada solusi dalam kendali kita.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Re-registrasi model sebagai versi baru** — tidak dipertimbangkan serius: tidak menyelesaikan akar masalah (OS registrasi tetap Windows), dan mengubah nomor versi `champion` tanpa alasan substantif (model tidak berubah, cuma path metadata).
- **Patch manual S3 SAJA tanpa perbaikan kode** — DITOLAK: hanya menutup gejala untuk versi 1, bug akan muncul lagi di setiap registrasi versi baru dari Windows (M2.8).

### 7. Prefect Managed tidak bisa jalankan model LightGBM — DITERIMA sebagai keterbatasan

**Keputusan:** Verifikasi Managed (Task 11) diterima SEBAGIAN — task non-LightGBM (`extract_raw_data`, gerbang kualitas data M2.4) terbukti sukses di Managed work pool, tapi `score_batch` (memuat model LightGBM) gagal (`libgomp.so.1` hilang, library sistem yang tidak bisa diinstal lewat `pip_packages` Managed). Verifikasi end-to-end skala penuh TETAP lewat run lokal (Task 10) sebagai bukti utama KK1. Dicatat detail lengkap di `docs/keterbatasan-diterima.md` KD-1 (dokumen backlog project-wide baru, diminta user eksplisit di milestone ini supaya berguna untuk milestone-milestone lain yang mungkin bersinggungan).

**Kenapa:** Diriset — ini gap packaging upstream LightGBM yang sudah diketahui ([microsoft/LightGBM#4484](https://github.com/microsoft/LightGBM/issues/4484)), tidak ada solusi pip-only yang reliable, dan Prefect Managed tidak memberi akses instalasi paket sistem level OS. User memilih menerima keterbatasan ini (dicatat jelas) daripada memindahkan arsitektur ke work pool yang butuh hosting sendiri (`process`/Docker) yang mengembalikan sebagian masalah hosting yang coba dihindari M2.1.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Pindah ke Prefect `process`/Docker work pool yang di-host sendiri** — ditawarkan sebagai alternatif (worker lokal, dinyalakan manual saat perlu, konsisten "bukan jadwal rutin aktif") tapi user memilih menerima keterbatasan Managed alih-alih pindah arsitektur lagi.
- **Compile LightGBM dari source (`pip install --no-binary`)** — tidak viable: masih butuh OpenMP dev headers/compiler di container yang juga tidak tersedia di Managed.

### 8. KD-1 diatasi untuk kebutuhan run terjadwal: `batch_scoring_flow()` via GitHub Actions, bukan Prefect Managed

**Muncul saat:** 2026-08-13, follow-up di luar checkpoint asli milestone ini -- dipicu percakapan terpisah yang menemukan `telco_customers_synthetic` ternyata sudah berisi 1.000 baris (generator sudah pernah dijalankan user, di luar sesi manapun yang tercatat) dan pemicu peninjauan ulang KD-1 ("kebutuhan run LightGBM terjadwal rutin muncul nyata") jadi relevan secara nyata, bukan hipotetis.

**Keputusan:** Ditambahkan `.github/workflows/batch-scoring.yml` -- trigger `workflow_dispatch` (**manual, BUKAN cron aktif**), `runs-on: ubuntu-latest`, menjalankan `batch_scoring_flow()` LANGSUNG lewat `python -m orchestration.flows.batch_scoring` (bukan lewat deployment/work pool Prefect Managed sama sekali). `@flow`/`@task` tetap melapor ke Prefect Cloud lewat `PREFECT_API_KEY`/`PREFECT_API_URL` yang sudah ada (M2.1) -- histori run tetap tercatat di Prefect Cloud, cuma mekanisme trigger/scheduling-nya pindah ke GitHub Actions. `orchestration/flows/batch_scoring.py` ditambah env var `BATCH_SCORING_LIMIT` di blok `__main__` supaya run verifikasi terkontrol bisa dipicu tanpa argumen CLI (kosong = perilaku lama, skala penuh).

**Kenapa:** `ubuntu-latest` TERBUKTI tidak kena `libgomp.so.1` -- sudah terbukti untuk `integration-tests` (M2.7, memuat model yang sama tiap push), sekarang dikonfirmasi juga untuk `score_batch` sungguhan (lihat Verifikasi di bawah). Dibanding opsi lain yang dipertimbangkan (lihat di bawah), ini tidak menambah akun/kredensial/infra eksternal baru -- GitHub Secrets yang dipakai sudah terprovisioning sejak M2.7.

**TIDAK ditambahkan cron aktif** -- `batch_scoring_flow()` masih hardcode membaca `telco_customers_source` (594rb baris statis, TIDAK diubah keputusan ini). Jadwal rutin sekarang akan menghasilkan prediksi duplikat identik tanpa informasi baru, persis pola yang sudah ditolak Keputusan #2 di atas -- cutover ke `telco_customers_synthetic` (KT-1 Fase 2) adalah keputusan terpisah yang belum diambil, mencakup 3 blocker lain (`SOURCE_TABLE` hardcoded, role `batch_reader` tanpa izin baca tabel synthetic, tidak ada mekanisme event/trigger). User eksplisit memilih ini sebelum implementasi (lihat Verifikasi).

**Verifikasi (bukti nyata, bukan asumsi):**
- Trigger `gh workflow run batch-scoring.yml -f limit=1000` → run [31694778869](https://github.com/Ardiyanto24/telco-churn-mlops/actions/runs/31694778869) **SUCCESS** (1m40s). Log: `extract_raw_data` 1000 baris, gerbang kualitas PASS, `score_batch` **Scored 1000 baris, model_version=1** (LightGBM dimuat sukses, TIDAK ADA error `libgomp.so.1`), `write_predictions` 1000 baris (`batch_run_id=ca721f01-acdd-4dc2-931f-3497242b7137`).
- Query langsung `predictions.batch_predictions WHERE batch_run_id='ca721f01-...'` → 1000 baris, 0 kolom lineage NULL (`model_version='1'`, `model_alias='champion'`, `flow_run_id` terisi UUID valid).
- Query langsung Prefect Cloud API (`client.read_flow_run(...)`) untuk `flow_run_id` di atas → nama `boisterous-wildcat`, `state_name='Completed'`, `start_time`/`end_time` valid -- mengonfirmasi tracking Prefect Cloud tetap bekerja meski trigger bukan dari deployment Prefect.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Prefect Cloud push work pool (Cloud Run/ECS/ACI) + custom Docker image ber-`libgomp1`** -- lebih "native Prefect" (jadwal `cron=` asli bisa dipakai lagi), tapi butuh akun cloud provider (AWS/GCP/Azure) baru yang TIDAK ada di proyek ini (kredensial AWS yang ada sekarang cuma untuk endpoint S3-compatible Supabase, bukan compute AWS sungguhan) -- infra+cost+secret baru yang belum sepadan untuk kebutuhan sekarang.
- **Self-host Prefect work pool (`process`/Docker)** -- opsi yang sudah disebut eksplisit di KD-1 sendiri dan sudah pernah ditolak user di Keputusan #7 (mengembalikan beban hosting yang M2.1 sengaja hindari). Tidak dipertimbangkan ulang serius karena opsi GitHub Actions muncul sebagai alternatif yang lebih murah tanpa trade-off itu.
- **Aktifkan cron sekarang juga (meski sumber masih statis)** -- ditawarkan eksplisit ke user, DITOLAK: akan menumpuk baris prediksi duplikat identik di `predictions.batch_predictions`, kontradiksi langsung dengan Keputusan #2 tanpa alasan baru yang membenarkannya.
- **Tunda seluruhnya sampai cutover Fase 2 (KT-1) dibahas sebagai satu paket** -- ditawarkan eksplisit ke user, DITOLAK: KD-1 adalah blocker independen yang berlaku juga untuk kebutuhan LightGBM terjadwal di luar konteks synthetic (mis. Milestone 2.8 kalau sanity-check artifact perlu jalan di infra serupa Managed di masa depan) -- tidak perlu menunggu keputusan cutover yang lebih besar.

## Catatan: Temuan Salah Ketik di Dokumen Sumber

KK ketiga M2.5 (`mlops-02-pipeline-orchestration.md`) menyebut "verifikasi otomatis dibangun di **Milestone 2.6**" — ini tampak salah ketik: verifikasi parity otomatis sebenarnya dideskripsikan di **Milestone 2.7** ("CI/CD dan Verifikasi Parity Otomatis"); Milestone 2.6 adalah "Isolasi Beban terhadap PostgreSQL", tidak berkaitan dengan parity. Dicatat di sini sebagai temuan, dokumen sumber TIDAK diubah (bukan wewenang milestone ini).
