# Decisions — Milestone 2.7: CI/CD dan Verifikasi Parity Otomatis

## Temuan Kritis Sebelum Plan Ditulis

`.github/workflows/test.yml` sudah ada sejak Milestone 1.4, TAPI gagal di **SETIAP push** sejak repo terhubung ke GitHub (dikonfirmasi `gh run list` — seluruh run historis berstatus `failure`). Root cause: workflow mem-pin Python 3.11, tapi `numpy==2.5.2` (dikunci M1.2) mensyaratkan Python ≥3.12 — venv lokal proyek ini sebenarnya Python 3.13.12. Tidak pernah ketahuan karena tidak ada yang mengecek status Actions. Ini jadi prasyarat Checkpoint 1.

## Klarifikasi Sebelum Plan Disusun

1. **Gate 2 (kualitas data):** harus terotomatisasi, dipicu GitHub Actions — bukan cuma test korektnes kode atau CLI manual (arahan eksplisit user, setelah penjelasan trade-off).
2. **Gate 3 (parity):** aktifkan test M2.5 yang sudah ada, bukan bangun perbandingan baru (dikonfirmasi user).

## Keputusan Teknis

### 1. GitHub Actions terus dipakai

**Keputusan:** Lanjutkan `.github/workflows/test.yml`, bukan pindah tool.

**Kenapa:** Preseden M1.4, satu-satunya opsi tanpa infrastruktur tambahan mengingat repo sudah di-host GitHub (M2.1). Ini sesuai "Tool orchestrator, CI/CD, monitoring stack konkret" yang dokumen arsitektur Bagian 10 sengaja biarkan terbuka untuk digali "masing-masing pemilik saat implementasi" — sudah digali M1.4, tinggal dilanjutkan.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan — forced by preseden M1.4 dan hosting GitHub yang sudah ada.

### 2. Perbaiki bug CI lama (Python version mismatch) sebagai prasyarat Checkpoint 1

**Keputusan:** `test.yml` `python-version` "3.11" → "3.13" (samakan PERSIS venv lokal terverifikasi), `pyproject.toml` `requires-python` ">=3.11" → ">=3.12" (batas nyata numpy, dikonfirmasi dari log error pip: "2.5.0/2.5.1 Requires-Python >=3.12"), install step ditambah extra `[orchestration]` (prefect belum pernah terinstall CI, dibutuhkan `tests/orchestration/` untuk bisa di-collect).

**Kenapa:** Bug murni faktual (versi salah), bukan keputusan desain — evidence based dari log run CI sungguhan, bukan tebakan.

**Opsi yang Dipertimbangkan tapi Ditolak:** **Downgrade numpy ke versi 3.11-compatible** — DITOLAK: mengubah dependency yang sudah diverifikasi ekstensif (170 test lokal) demi menyamai CI yang salah konfigurasi, arah perbaikan terbalik (CI harus menyamai environment yang sudah terbukti benar, bukan sebaliknya).

### 3. Bug kedua ditemukan+diperbaiki: `orchestration/` tidak importable lewat bare `pytest`

**Keputusan:** Tambah `[tool.pytest.ini_options] pythonpath = ["."]` di `pyproject.toml`.

**Kenapa:** Ditemukan setelah bug #2 fix — CI lolos instalasi tapi gagal `ModuleNotFoundError: No module named 'orchestration'`. Root cause: `pytest tests/` (dipanggil langsung, dipakai CI) TIDAK otomatis menaruh root repo di `sys.path`, beda dari `python -m pytest` yang implisit menambahkannya (dipakai sepanjang sesi sebelumnya untuk verifikasi lokal, tanpa sadar menutupi bug ini). Reproducible lokal juga dengan bare `pytest`, dikonfirmasi sebelum menulis fix.

**Opsi yang Dipertimbangkan tapi Ditolak:** **Tambah `orchestration/__init__.py` di root** — tidak akan menyelesaikan masalah (root cause bukan soal package-ness `orchestration/`, tapi soal repo root tidak ada di `sys.path` sama sekali). **Selalu panggil `python -m pytest` di CI** — DITOLAK: `pythonpath` ini-option lebih robust, bekerja konsisten terlepas cara pytest dipanggil (bare `pytest` ATAU `python -m pytest`), tidak bergantung konvensi command yang bisa lupa diikuti siapa pun di masa depan.

### 4. Pisah gerbang unit-tests vs integration-tests via marker pytest

**Keputusan:** Marker `integration` ditambahkan HANYA ke 6 modul yang skip berdasarkan KREDENSIAL Supabase/MLflow (`test_batch_scoring.py`, `test_raw_schema_supabase.py`, `test_parity_real_artifact.py`, `test_e2e_parity.py`, `test_gate.py`, `test_baseline.py`) — BUKAN 3 modul lain (`test_registry.py`, `test_predictor.py`, `test_pyfunc_model.py`) yang skip karena FILE ARTIFACT LOKAL tidak ada (`artifacs/`, gitignored, tidak akan pernah ada di checkout CI apa pun kondisinya). `test.yml` direstrukturisasi jadi job `unit-tests` (`-m "not integration"`, tanpa secret) → `integration-tests` (`needs: unit-tests`, `-m integration`, dengan secret).

**Kenapa:** Kedua kategori skip PUNYA AKAR MASALAH BEDA — menambah secret tidak akan pernah membuat 3 modul kedua jalan di CI (file lokal tetap tidak ada), jadi menandainya `integration` (menyiratkan "akan jalan begitu secret ada") menyesatkan. Job berurutan (`needs:`) memberi semantik "gerbang gagal, gerbang berikutnya tidak jalan" yang eksplisit diminta KK sumber — tidak bisa dicapai dengan satu `pytest` invocation monolitik.

**Opsi yang Dipertimbangkan tapi Ditolak:** **Tandai SEMUA 9 modul sebagai integration** — DITOLAK: mengaburkan perbedaan real (credential-gated vs artifact-gated), berpotensi bikin orang berikutnya salah asumsi "tambah secret akan membuat semua ini jalan".

### 5. Bug ketiga ditemukan+diperbaiki: kuirk cache MLflow client lintas tracking-URI

**Keputusan:** Job `integration-tests` menjalankan `tests/orchestration/` sebagai invocation `pytest` TERPISAH (proses baru) dari sisa integration test lain, bukan satu perintah gabungan.

**Kenapa:** Ditemukan saat verifikasi lokal — menjalankan SELURUH test integration dalam SATU proses pytest membuat 2 test `test_batch_scoring.py` gagal palsu (`MlflowException: Registered model alias champion not found`), padahal alias itu VERIFIED ada dan benar saat dicek langsung. Dibuktikan lewat repro minimal (script standalone: query alias real registry OK → register bundle ke tracking URI SQLite sementara → switch balik ke tracking URI Postgres real → resolusi alias GAGAL) BUKAN bug kode `churn_prediction`, tapi kuirk `mlflow-skinny`: `MlflowClient` men-cache engine/store per tracking-URI di dalam proses yang sama tanpa pernah dispose — terbukti juga dari `PermissionError` file SQLite tidak bisa dihapus (`tempfile.TemporaryDirectory` cleanup) karena koneksi masih dipegang cache internal MLflow. Isolasi proses (2 invocation `pytest` terpisah) menghindari masalah ini sepenuhnya tanpa perlu memahami/menambal internal MLflow.

**Opsi yang Dipertimbangkan tapi Ditolak:** **Patch/reset cache internal MLflow secara eksplisit** (mis. `_get_store.cache_clear()`) — DITOLAK: bergantung detail implementasi privat MLflow yang bisa berubah antar versi, rapuh. **Reorder test dalam SATU proses supaya `tests/orchestration/` jalan duluan** — DITOLAK: rapuh terhadap penambahan test file baru di masa depan (siapa pun bisa menambah test yang pindah tracking URI tanpa sadar order matters); isolasi proses adalah fix struktural, bukan tergantung urutan collection.

### 6. Gate 2: otomatis via GitHub Actions, mode non-recording

**Keputusan:** Job CI baru `quality-data-check` (`needs: unit-tests`) memanggil `orchestration/ci_quality_check.py`, yang menjalankan `run_gate()` (parameter baru `record_history=False`) terhadap `telco_customers_source` LIVE. Verdict `stop` menggagalkan job.

**Kenapa:** Dikonfirmasi user eksplisit: "diintegrasikan" berarti terotomatisasi lewat GitHub Actions, bukan manual. Tapi memanggil `run_gate()` biasa (recording) dari CI TIAP PUSH akan mencemari `quality.gate_run_history` yang dipakai DAG produksi — persis root cause yang sudah 2x ditemukan (M2.5, M2.6). `record_history=False` (parameter baru, default `True` — perilaku DAG M2.5 TIDAK berubah) memberi verdict nyata TANPA menulis riwayat, menjawab kebutuhan otomatisasi tanpa mengulang bug yang sama.

**Opsi yang Dipertimbangkan tapi Ditolak (diajukan ke user sebelum klarifikasi final):**
- **Test korektnes kode saja (`tests/quality/` di gerbang unit test)** — DITOLAK user: tidak memenuhi "otomatis, dipicu GitHub Actions" terhadap data nyata.
- **CLI manual tanpa trigger CI otomatis** — DITOLAK user: sama alasannya, bukan otomatis.
- **Jadwalkan `run_gate()` recording penuh dari CI (cron)** — tidak dipilih: risiko pencemaran baseline TETAP ada (cuma beda pemicu, bukan beda mekanisme), dan jadi jadwal rutin otomatis pertama di proyek ini (bertentangan keputusan M2.5 belum aktifkan jadwal apa pun).

### 7. Gate 3: aktifkan test M2.5 existing, bukan bangun baru

**Keputusan:** Set 10 kredensial sebagai GitHub Secrets (lewat `gh secret set`, izin eksplisit diminta lebih dulu) supaya `test_batch_predictions_match_direct_predict_active_call` (M2.5) berhenti auto-skip dan jadi gerbang CI sungguhan. Parity penuh vs real-time API SUNGGUHAN dicatat sebagai **KT-7** (`docs/keputusan-tertunda.md`), menunggu M3.x.

**Kenapa:** Dikonfirmasi user. Test ini adalah proxy terbaik yang tersedia SEKARANG (`predict_active()` satu-satunya kode "real-time" yang eksis) — konsisten bunyi KK3 M2.5 ("verifikasi awal parity sebelum otomatis dibangun di Milestone 2.7"). Diverifikasi lewat uji coba terkontrol (Keputusan #9) — gerbang terbukti menangkap penyimpangan nyata, bukan cuma lolos di kondisi normal.

**Opsi yang Dipertimbangkan tapi Ditolak:** **Perluas cakupan sampel/kasus tepi test parity sekarang** — tidak dipilih user (opsi kedua yang diajukan): lebih banyak kerja implementasi untuk cakupan yang secara konsep sama (masih `predict_active()` vs batch, bukan real-time API sungguhan) — deprioritaskan, KT-7 mencatat parity penuh sebagai follow-up M3.x.

### 8. Provisioning GitHub Secrets: 10 kredensial + 1 yang sempat terlewat

**Keputusan:** 10 secret di-provisioning via `gh secret set` (SUPABASE_DB_URL, BATCH_READER_DB_URL, BATCH_WRITER_DB_URL, QUALITY_GATE_DB_URL, MLFLOW_TRACKING_URI, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, MLFLOW_ARTIFACT_BUCKET, PREFECT_API_KEY, PREFECT_API_URL) — nilai tidak pernah dicetak ke log/chat. `MLFLOW_S3_ENDPOINT_URL` sempat TERLEWAT dari daftar awal (kesalahan proses saya menyusun daftar dari `.env`, bukan gap arsitektural) — ketahuan dari kegagalan CI sungguhan (`ValueError: Invalid endpoint:`, boto3 menerima string kosong), diperbaiki dengan menambah 1 secret lagi lalu `gh run rerun --failed` (tidak perlu commit baru).

**Kenapa:** Izin eksplisit diminta dan didapat sebelum provisioning (kredensial adalah konfigurasi sensitif). Kesalahan #11 murni proses (kurang teliti menyusun daftar), langsung ketahuan+diperbaiki dari bukti run CI sungguhan, bukan diasumsikan benar.

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada alternatif dipertimbangkan — forced correction begitu bug ketahuan dari run nyata.

### 9. Gate 4: dokumentasi konvensi saja, bukan job placeholder

**Keputusan:** Komentar di `test.yml` (baris akhir file) menjelaskan konvensi `needs: [unit-tests, quality-data-check, integration-tests]` untuk job deployment gate Orang #3 (M3.x) — TIDAK ada job GitHub Actions baru yang dibuat untuk ini.

**Kenapa:** M3.x belum ada kode/service apa pun untuk digerbangi — job placeholder yang tidak melakukan apa-apa cuma kosmetik (selalu "hijau" tanpa memverifikasi apa pun nyata), berisiko menyesatkan (terlihat seperti ada gerbang deployment padahal tidak). Dokumentasi konvensi cukup untuk memenuhi KK ("Orang #3 berhasil mengintegrasikan... tanpa perlu membangun infrastruktur CI terpisah") — cara pemenuhannya lewat kejelasan struktur, bukan kode dummy.

**Opsi yang Dipertimbangkan tapi Ditolak:** **Job placeholder kosong (`echo "TODO M3.x"`)** — DITOLAK: di luar cakupan membangun kapabilitas untuk pekerjaan yang belum mulai, berisiko menyesatkan status CI.

## Catatan: Keterbatasan yang Ditemukan, Bukan Diperbaiki (Bukan Bug M2.7)

**3 modul test (`test_registry.py`, `test_predictor.py`, `test_pyfunc_model.py`) SELAMANYA akan skip di CI**, berapa pun secret ditambahkan — skip condition-nya bergantung `artifacs/model/model_final.joblib`+`artifacs/proprocessor/preprocessor.joblib` yang GITIGNORED, tidak akan pernah ada di checkout CI mana pun. Ini BUKAN bug M2.7 (skip condition ini sudah ada sejak M1.5, sebelum CI pernah berhasil jalan sama sekali) — dicatat sebagai temuan relevan untuk **Milestone 2.8** (sanity check artifact sebelum registrasi versi baru — mekanisme itu perlu mikir ulang bagaimana artifact tersedia di lingkungan CI/otomatis, bukan mengandalkan file lokal).
