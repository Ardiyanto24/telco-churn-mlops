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

## Catatan: Temuan Salah Ketik di Dokumen Sumber

KK ketiga M2.5 (`mlops-02-pipeline-orchestration.md`) menyebut "verifikasi otomatis dibangun di **Milestone 2.6**" — ini tampak salah ketik: verifikasi parity otomatis sebenarnya dideskripsikan di **Milestone 2.7** ("CI/CD dan Verifikasi Parity Otomatis"); Milestone 2.6 adalah "Isolasi Beban terhadap PostgreSQL", tidak berkaitan dengan parity. Dicatat di sini sebagai temuan, dokumen sumber TIDAK diubah (bukan wewenang milestone ini).
