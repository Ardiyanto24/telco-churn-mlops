# Logs — Milestone 2.5: Batch Scoring DAG

## Checkpoint 1 — Fondasi: perluasan package + sentralisasi + provisioning

**Mulai:** 2026-08-13.

**Task 1:** `RAW_PASCAL_TO_SNAKE` dipindah ke `src/churn_prediction/schema/column_mapping.py`, 3 file test (`test_e2e_parity.py`, `test_parity_real_artifact.py`, `test_raw_schema_supabase.py`) diupdate untuk import dari sana.

**Task 2:** `predict_active()` ditambah ke `predictor.py`. **Bug ditemukan+diperbaiki saat implementasi:** refactor pertama keliru memanggil `registry.load_*` SEBELUM validasi `RawDataSchema` (regresi dari kontrak M1.5 yang wajib validasi duluan) — ditemukan lewat sanity check manual sebelum test formal ditulis, diperbaiki (`_attach_lineage` helper, validasi tetap di awal `predict()`/`predict_active()`).

**Task 3:** Test `predict_active()` ditulis (round-trip vs `predict()`, model_version konkret bukan alias, validasi-sebelum-registry). **Verifikasi:** `pytest tests/inference/test_predictor.py -v` → 10 passed. `pytest tests/ -q` penuh → 166 passed.

**Task 4:** `infra/sql/2.5_batch_scoring_roles.sql` disiapkan (role `batch_reader`/`batch_writer`, tabel `predictions.batch_predictions`). Konfirmasi eksplisit diminta — dikonfirmasi, dijalankan.

**Temuan (saat verifikasi Task 4):** `batch_reader` `SELECT count(*) FROM telco_customers_source` mengembalikan **0** meski `GRANT SELECT` berhasil. Investigasi: `SELECT relrowsecurity FROM pg_class WHERE relname='telco_customers_source'` → `true`, `SELECT * FROM pg_policies WHERE tablename='telco_customers_source'` → kosong (0 policy). Root cause: Postgres RLS aktif tanpa policy = deny-all untuk role non-owner, terlepas dari GRANT. **Perbaikan:** `CREATE POLICY batch_reader_select ON telco_customers_source FOR SELECT TO batch_reader USING (true);` — re-verifikasi: count=594194, benar. `infra/sql/2.5_batch_scoring_roles.sql` diperbarui mencantumkan policy ini.

**Selesai, commit:** `adc2bc4` (feat, tasks 1-3), `9739b07` (feat, task 4).

## Checkpoint 2 — Task DAG dan orkestrasi flow

**Task 5-9:** `orchestration/flows/batch_scoring.py` ditulis lengkap (`extract_raw_data`, `run_quality_gate_task`, `score_batch`, `write_predictions`, `batch_scoring_flow`). **Bug ditemukan+diperbaiki saat sanity check:** `get_run_logger()` gagal dengan `MissingContextError` saat task dipanggil lewat `.fn()` (tanpa konteks run Prefect aktif) — diperbaiki dengan helper `_get_logger()` yang fallback ke `logging` standar.

**Verifikasi:** sanity check tiap task via `.fn()` untuk 500 baris sukses (dibersihkan sesudahnya). Flow LENGKAP (bukan `.fn()`) dijalankan sungguhan untuk sampel 2000 baris — 4 task selesai berurutan sesuai dependency, tercatat di Prefect Cloud, 2000 baris terverifikasi di `predictions.batch_predictions`. `pytest tests/ -q` penuh → 166 passed.

**Selesai, commit:** `f703ee2` (feat).

## Checkpoint 3 — Verifikasi (skala penuh, Managed, parity, lineage, kegagalan terkontrol)

**Task 10:** `batch_scoring_flow()` dijalankan LOKAL untuk SELURUH 594.194 baris. **Hasil:** 594.194 baris tertulis, 0 kolom lineage NULL, 594.194 `customer_id` distinct (diverifikasi query langsung). **Total waktu: 551.5 detik (~9.2 menit)** — signifikan lebih lama dari estimasi awal (1-2 menit, diekstrapolasi dari sampel 20rb baris) karena overhead model-load (~20-25s) tidak dominan lagi di skala penuh dan waktu tulis 594rb baris dalam satu transaksi meaningful (~4 menit). Dicatat jujur sebagai koreksi estimasi, bukan disembunyikan.

**Task 11 (deploy + trigger Managed):**
1. `orchestration/deploy_batch_scoring.py` ditulis — deploy TANPA jadwal cron aktif, kredensial sebagai Prefect Secret block (`{{ prefect.blocks.secret.<slug> }}`), `job_variables.pip_packages` install `churn_prediction` langsung dari GitHub (`git+https://...`).
2. Push 3 commit Checkpoint 1-2 ke `origin/main` (konfirmasi eksplisit diminta — dikonfirmasi) — dibutuhkan supaya `flow.from_source()` bisa menarik kode.
3. Deploy berhasil, 7 Secret block dibuat. Trigger manual pertama (`limit=1000`) → **FAILED**. Log: gerbang kualitas data verdict `stop` ("Volume menyimpang 99.9% dari baseline"). **Diagnosis:** baseline `quality.gate_run_history` untuk `telco_customers_source` tercemar oleh run-run verifikasi sebelumnya dengan skala sangat berbeda (500/2000/594194 baris) — rata-rata baseline jadi ~198.898, membuat sampel kecil apa pun berikutnya otomatis "anjlok >50%". **Ini gerbang bekerja sesuai desain, bukan bug** — tapi riwayatnya perlu direset. Baseline dibersihkan (`DELETE FROM quality.gate_run_history WHERE source_table='telco_customers_source'`), fixture test (lihat Task 12-14) diperbaiki untuk membersihkan baseline juga (bukan cuma `predictions.batch_predictions`).
4. Trigger manual kedua (`limit=1000`, baseline bersih) → **FAILED lagi**, alasan BEDA: `OSError: libgomp.so.1: cannot open shared object file`. **Diagnosis:** task `extract_raw_data` dan gerbang kualitas data SUKSES di Managed (bukti mekanisme deployment+scheduling Prefect Cloud bekerja) — tapi `score_batch` (memuat model LightGBM) gagal. Root cause: `libgomp.so.1` adalah library sistem (bukan Python package), gap packaging upstream LightGBM yang diketahui ([microsoft/LightGBM#4484](https://github.com/microsoft/LightGBM/issues/4484)), Prefect Managed tidak beri akses `apt-get`.
5. **Sambil investigasi traceback,** ditemukan bug LAIN yang lebih fundamental di traceback yang sama: `FileNotFoundError` path artifact tercampur separator Windows+Unix (`/tmp/.../artifacts\bundle.joblib`) — ini muncul di percobaan run Managed PERTAMA (sebelum baseline dibersihkan, jadi tertutup oleh kegagalan gerbang kualitas terlebih dahulu secara berurutan; baru kelihatan di percobaan run KEDUA). Root cause: bug upstream MLflow ([mlflow/mlflow#11862](https://github.com/mlflow/mlflow/issues/11862)) — model diregistrasi dari Windows (M2.1) menyimpan path relatif artifact dengan backslash literal ke manifest `MLmodel`, tidak portable ke Linux. **Diperbaiki:** manifest `MLmodel` di Supabase Storage di-patch langsung (`path: artifacts\bundle.joblib` → `artifacts/bundle.joblib`), `registry.py` `register_model()` diperbaiki (`.as_posix()`) untuk registrasi versi mendatang.
6. Trigger manual KETIGA (`limit=1000`, path sudah diperbaiki) → **masih FAILED**, tapi progress lebih jauh (extract+gate PASS, sampai ke `score_batch`) sebelum kena `libgomp.so.1` (temuan poin 4) — ini MENGONFIRMASI patch path berhasil (bug artifact loading sudah tidak muncul lagi), sisa kegagalan murni `libgomp.so.1`.
7. **Keputusan user:** terima keterbatasan `libgomp.so.1` (KD-1), TIDAK pindah ke work pool lain. Diminta dokumen baru `docs/keterbatasan-diterima.md` untuk mencatat ini + berguna milestone mendatang — dibuat, dirujuk di `CLAUDE.md`/`AGENT.md`.

**Task 12-14 (test):** `tests/orchestration/test_batch_scoring.py` ditulis — parity (KK3), traceability (KK4), rollback+retry (KK2). **Bug ditemukan+diperbaiki saat test pertama:** perbandingan `model_version` (int dari `resolve_alias_version()`) vs kolom Postgres (text) gagal karena type mismatch (`1 != '1'`) — diperbaiki dengan `str()` cast eksplisit di assertion. **Verifikasi final:** `pytest tests/orchestration/test_batch_scoring.py -v` → **4 passed** terhadap infrastruktur sungguhan (Supabase + MLflow + Prefect).

**Setelah baseline direset + fixture diperbaiki, run Managed KEEMPAT** (`limit=1000`) dipicu ulang untuk memastikan tidak ada regresi baru dari perbaikan test — hasil konsisten dengan temuan poin 6 (gagal di `libgomp.so.1`, sesuai ekspektasi, diterima).

**Selesai, commit:** `a3eb681` (feat, deploy script+test), `68f870a` (fix, path artifact), `b0a455e` (docs, keterbatasan-diterima.md).
