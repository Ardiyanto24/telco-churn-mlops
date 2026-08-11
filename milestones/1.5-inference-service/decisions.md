# Decisions — Milestone 1.5: Inference Service Package

## Klarifikasi Sebelum Plan Disusun

Lima pertanyaan diajukan ke user sebelum plan ditulis (bukan diasumsikan), karena M1.5 punya beberapa keputusan desain yang genuinely terbuka dan berdampak material:

1. MLflow macam apa dipakai untuk kebutuhan uji KK M1.5 sendiri, mengingat repo belum punya MLflow apa pun dan `mlops-02-pipeline-orchestration.md` Milestone 2.1 eksplisit memberi tanggung jawab "MLflow model registry terpasang" ke Orang #2, bukan Orang #1?
   → Jawaban: **tracking URI lokal file-based** (`file:./mlruns`, gitignored).
2. Apakah `model_final.joblib` diregistrasi sebagai versi produksi resmi di M1.5 ini, atau ditunda ke Milestone 2.1 sesuai pembagian dokumen?
   → Jawaban: **ditunda ke Milestone 2.1** — M1.5 cukup membuktikan mekanisme *load-by-version* bekerja.
3. Kontrak output `predict()` — label saja+probability, atau ditambah metadata lineage?
   → Jawaban: **label + probability + metadata lineage** (versi model, waktu prediksi).
4. Kontrak input `predict()` — DataFrame saja, atau juga menerima dict/record tunggal?
   → Jawaban: **DataFrame saja**.
5. Preprocessor+model — dibundel jadi satu artifact MLflow, atau dipisah (model dari MLflow, preprocessor lokal)?
   → Jawaban: **dibundel jadi satu custom `mlflow.pyfunc.PythonModel`**.

## Keputusan Teknis

### 1. MLflow lokal file-based, eksplisit sementara — bukan setup resmi M2.1

**Keputusan:** `mlflow.set_tracking_uri()` memakai URI dari env var `MLFLOW_TRACKING_URI` (pola sama `.env`/`.env.example` seperti `SUPABASE_DB_URL`), default `file:./mlruns` kalau tidak diset. Folder `mlruns/` ditambahkan ke `.gitignore` (pola sama `artifacs/`). Nama model teregistrasi: `churn_prediction_model` (konstanta di `inference/constants.py`).

**Kenapa:** Dikonfirmasi user (opsi 1 dari 3 pilihan). Tidak hardcode path supaya package tetap bisa dipanggil dari environment/proyek berbeda (KK1) tanpa ubah kode — hanya env var yang beda. `file:./mlruns` cukup untuk membuktikan mekanisme versioning bekerja, tanpa membangun infrastruktur server yang jadi tanggung jawab M2.1.

### 2. Registrasi di M1.5 bersifat uji, registrasi resmi tetap M2.1

**Keputusan:** M1.5 meregistrasi 2 versi ke MLflow lokal: **versi 1** = bundle sungguhan (`model_final.joblib` + preprocessor ter-graft + threshold 0.6238, hasil KK2), **versi 2** = bundle sengaja berbeda secara terukur (model SAMA tapi threshold sengaja diubah, mis. 0.5) — dibuat khusus untuk membuktikan KK3 (mekanisme load-by-version benar-benar mengambil versi yang diminta, bukan cache/selalu-versi-terakhir), bukan kandidat model kedua yang sungguhan. `report.md` menyatakan eksplisit: ini BUKAN registrasi resmi "versi awal produksi" — itu tetap output Milestone 2.1.

**Kenapa:** Dikonfirmasi user (opsi "ditunda ke M2.1"). KK3 M1.5 tetap perlu dibuktikan dengan sesuatu yang nyata (bukan diasumsikan bekerja) — memakai versi uji yang jelas dibedakan (threshold berbeda) memberi bukti yang bersih dan terverifikasi tanpa berpura-pura versi 2 adalah kandidat produksi sungguhan.

### 3. Kontrak output: DataFrame dengan label+probability+lineage

**Keputusan:** `predict(df, model_version)` mengembalikan `pandas.DataFrame` (urutan baris = urutan input) dengan kolom: `churn_probability` (float, `predict_proba(X)[:,1]`), `churn_label` (int 0/1, dari threshold yang tersimpan di dalam bundle yang dimuat — bukan hardcode ulang di `predictor.py`), `model_version` (str), `predicted_at` (ISO8601 UTC timestamp saat prediksi dijalankan).

**Kenapa:** Dikonfirmasi user (opsi "Label + probability + metadata lineage"). DataFrame (bukan dataclass/dict) konsisten dengan pola input DataFrame-only (Keputusan #4) dan pola M1.2/M1.3 yang sudah mapan. Threshold disimpan di dalam bundle (bukan konstanta terpisah di `predictor.py`) supaya versi 2 uji (Keputusan #2, threshold beda) benar-benar menghasilkan label berbeda — bukti KK3 yang valid.

### 4. Kontrak input: DataFrame saja, divalidasi `raw_schema` di dalam `predict()`

**Keputusan:** `predict()` menerima `pandas.DataFrame`, memvalidasi lewat `churn_prediction.schema.raw_schema` **di dalam** fungsi (bukan mengasumsikan pemanggil sudah validasi) sebelum diteruskan ke pipeline — data tidak lolos validasi menghasilkan error eksplisit, bukan prediksi diam-diam salah. Pemanggil (Orang #2: row Postgres; Orang #3: payload `request_schema` Pydantic) bertanggung jawab mengonversi bentuk data mereka ke DataFrame sebelum memanggil.

**Kenapa:** Dikonfirmasi user (opsi "DataFrame saja"). Validasi tetap dilakukan di dalam `predict()` (bukan cuma didokumentasikan sebagai "tanggung jawab pemanggil") karena prinsip arsitektur eksplisit: "Kegagalan API harus memberi error terstruktur; jangan pernah menyamarkan kegagalan sebagai prediksi valid" (CLAUDE.md) dan modul "tidak boleh ditulis dengan asumsi dipanggil dari satu tempat saja" — mempercayai pemanggil sudah validasi adalah asumsi implisit yang persis ingin dihindari.

### 5. Bundle tunggal via custom `mlflow.pyfunc.PythonModel`

**Keputusan:** `inference/pyfunc_model.py` berisi `ChurnPyfuncModel(mlflow.pyfunc.PythonModel)` — `load_context` memuat satu file joblib berisi `{"pipeline": <PreprocessingPipeline ter-graft>, "model": <VotingClassifier>, "threshold": <float>}`, `predict(context, model_input)` menjalankan `pipeline.transform()` → `model.predict_proba()[:,1]` → threshold → mengembalikan DataFrame `churn_probability`+`churn_label`. Bundle dibangun oleh `inference/registry.py:build_bundle()` yang memanggil ulang mekanisme grafting M1.2 (lihat Keputusan #6) lalu di-`mlflow.pyfunc.log_model(artifacts={"bundle": <path joblib>})` + `mlflow.register_model()`.

**Kenapa:** Dikonfirmasi user (opsi "Bundel jadi satu pyfunc MLflow"). Satu artifact per versi berarti versi model dan versi preprocessor yang kompatibel dengannya selalu bergerak bersama — rollback (ganti penanda versi aktif di registry) otomatis memakai preprocessor yang tepat tanpa langkah manual tambahan, persis prinsip Bagian 5.4 dokumen arsitektur (kompatibilitas skema saat promosi/rollback versi).

### 6. Sentralisasi logika grafting dari test-only ke `transform/` produksi

**Keputusan:** `_notebook_reference.py` (class referensi PascalCase, saat ini `tests/transform/_notebook_reference.py`) dipindah (`git mv`) ke `src/churn_prediction/transform/_notebook_reference.py` (modul privat, prefix `_` menandakan bukan API publik). Logika shim+load (`_load_real_preprocessor`) dan grafting (`_graft_our_pipeline`) dari `test_parity_real_artifact.py` diekstrak jadi fungsi produksi `load_fitted_pipeline(preprocessor_path) -> PreprocessingPipeline` di `src/churn_prediction/transform/artifact_loader.py`. `test_parity_real_artifact.py` (M1.2) di-refactor memanggil fungsi ini alih-alih duplikasi kode — diverifikasi test itu TETAP hijau tanpa perubahan perilaku (murni pemindahan lokasi kode, bukan logika baru).

**Kenapa:** Ini bukan keputusan baru yang perlu ditanyakan ke user — dipaksa oleh prinsip "satu sumber kebenaran" yang sudah berlaku sejak M1.3. Sebelum M1.5, teknik grafting cuma ada sebagai test-only scaffolding (M1.2 Checkpoint 5) — tapi `registry.build_bundle()` sekarang butuh cara PRODUKSI untuk memuat+graft `preprocessor.joblib`, bukan cuma untuk uji. Duplikasi (satu salinan di `tests/`, satu lagi ditulis ulang di `src/`) berisiko drift kalau notebook reference class berubah suatu saat dan hanya satu sisi yang disinkronkan.

### 7. (Turunan, ditemukan saat eksekusi Checkpoint 0) Backend lokal: SQLite (`sqlite:///mlruns.db`), bukan literal `file:./mlruns`

**Keputusan:** `DEFAULT_TRACKING_URI = "sqlite:///mlruns.db"` (bukan `file:./mlruns` seperti disebut di Keputusan #1 semula). File database SQLite + folder `mlruns/` (artifact store default) sama-sama lokal, gitignored, tanpa proses server terpisah — instalasi `mlflow-skinny` (bukan `mlflow` penuh, lihat Keputusan #8) tanpa dependency tambahan.

**Kenapa:** Bukan keputusan desain baru — dipaksa oleh temuan teknis konkret saat instalasi. `mlflow==3.15.1` (versi stabil terkini saat milestone ini dikerjakan) menaruh filesystem tracking backend murni (`file:./mlruns`) ke **maintenance mode**: mencoba `mlflow.start_run()` dengan tracking URI `file:` menghasilkan `MlflowException` eksplisit ("filesystem tracking backend ... is in maintenance mode ... will not receive further updates ... set MLFLOW_ALLOW_FILE_STORE=true to opt out"). Dua opsi: (a) set env var opt-out untuk tetap pakai backend yang secara eksplisit dinyatakan MLflow sendiri tidak akan menerima update lagi, atau (b) pindah ke backend SQLite — sama-sama lokal/tanpa server, tapi bukan backend yang sudah dinyatakan deprecated. Dipilih (b) karena memenuhi maksud asli Keputusan #1 user (lokal, sementara, cukup untuk uji KK M1.5) tanpa membangun di atas fondasi yang MLflow sendiri sedang deprecate — diverifikasi lewat smoke test langsung (register 2 versi model, keduanya berhasil dimuat independen lewat `models:/<name>/<version>`) sebelum dipakai di kode produksi.

### 8. (Turunan) Dependency: `mlflow-skinny`, bukan `mlflow` penuh

**Keputusan:** `pyproject.toml` menambahkan `mlflow-skinny` (bukan `mlflow`) ke `dependencies` inti.

**Kenapa:** Ditemukan saat instalasi: `mlflow` (paket penuh) mensyaratkan `pandas<3` sebagai dependency-nya sendiri — bertentangan langsung dengan `pandas==3.0.5` yang sudah dikunci M1.2 Checkpoint 6 berdasarkan environment yang TERBUKTI jalan dengan `preprocessor.joblib` asli DS (mengganti pandas berisiko diam-diam mengubah perilaku modul `transform` yang sudah diverifikasi 100% branch coverage). `mlflow-skinny` menyediakan seluruh API yang dipakai M1.5 (`mlflow.pyfunc.PythonModel`, `log_model`, `register_model`, `load_model`, tracking client) TANPA dependency ke pandas/numpy/scikit-learn sama sekali (dicek via `importlib.metadata.requires`) — cocok karena M1.5 memakai custom pyfunc (Keputusan #5), bukan flavor `mlflow.sklearn` yang butuh paket penuh. Diverifikasi: `pandas`/`numpy`/`scikit-learn` tetap persis di versi M1.2 (`3.0.5`/`2.5.2`/`1.6.1`) setelah instalasi `mlflow-skinny`.
