# Logs — Milestone 1.5: Inference Service Package

## Checkpoint 0 — Keputusan + scaffold

**Mulai:** 2026-08-11.

**Klarifikasi sebelum plan:** 5 pertanyaan diajukan lewat AskUserQuestion (MLflow lokal vs server, registrasi resmi model_final.joblib sekarang vs M2.1, kontrak output, kontrak input, bundling preprocessor+model) — semua dijawab user sebelum plan ditulis. Detail lengkap di `decisions.md`.

**Temuan Task 0b (scaffold dependency) — dua penyimpangan dari asumsi awal plan, keduanya diverifikasi konkret sebelum diputuskan, dicatat sebagai Keputusan #7 dan #8 di `decisions.md`:**

1. `pip install mlflow` (paket penuh) menarik `pandas<3` sebagai dependency-nya sendiri dan **mendowngrade pandas dari 3.0.5 (terkunci M1.2) ke 2.3.3** secara otomatis. Ini konflik langsung dengan dependency yang sudah dikunci berdasarkan environment TERBUKTI jalan dengan `preprocessor.joblib` asli DS. Diverifikasi: `mlflow-skinny` (variant client-only) TIDAK punya dependency ke pandas/numpy/scikit-learn sama sekali (`importlib.metadata.requires('mlflow-skinny')` — list kosong untuk ketiganya). Uninstall `mlflow` penuh, reinstall `pandas==3.0.5`, konfirmasi `mlflow-skinny` tetap menyediakan `mlflow.pyfunc.PythonModel`/`log_model`/`register_model`/`load_model` (seluruh API yang dipakai M1.5 karena kita pakai custom pyfunc, bukan flavor `mlflow.sklearn`). Diputuskan: pakai `mlflow-skinny==3.15.1`, bukan `mlflow`.

2. Percobaan awal `mlflow.set_tracking_uri("file:./mlruns")` (URI literal yang disebut di plan Keputusan #1) gagal dengan `MlflowException`: filesystem tracking backend murni sudah masuk **maintenance mode** di mlflow 3.15.1 ("will not receive further updates ... set MLFLOW_ALLOW_FILE_STORE=true to opt out"). Smoke test dengan `sqlite:///mlruns.db` (backend lokal alternatif, tetap tanpa server) berhasil penuh: register 2 versi model, keduanya berhasil dimuat independen lewat `models:/<name>/<version>`. Diputuskan: `DEFAULT_TRACKING_URI = "sqlite:///mlruns.db"`, bukan `file:./mlruns`.

**Verifikasi:** `pytest tests/ -q` → **123 passed** (termasuk `test_kk2_parity_against_real_artifact_on_supabase_data` yang benar-benar JALAN, bukan skip — `SUPABASE_DB_URL` tersedia di environment ini via `.env`). Membuktikan penambahan `mlflow-skinny` tidak mengganggu dependency M1.2-1.4 yang sudah terkunci.

**File disentuh:** `pyproject.toml` (tambah `mlflow-skinny==3.15.1`), `.gitignore` (tambah `mlruns/`, `mlruns.db`), `.env.example` (tambah `MLFLOW_TRACKING_URI`), `src/churn_prediction/inference/{__init__,constants}.py` (skeleton), `milestones/1.5-inference-service/decisions.md`.

## Checkpoint 1 — Sentralisasi artifact loading (Keputusan #6)

`git mv tests/transform/_notebook_reference.py src/churn_prediction/transform/_notebook_reference.py`. Dibuat `src/churn_prediction/transform/artifact_loader.py` dengan dua fungsi publik: `load_original_preprocessor(path)` (load mentah, ground truth) dan `load_fitted_pipeline(path)` (load+graft, siap `transform()` langsung) -- gabungan `_load_real_preprocessor`+`_graft_our_pipeline` yang sebelumnya duplikat di `test_parity_real_artifact.py`.

`test_parity_real_artifact.py` di-refactor: hapus kedua fungsi lokal, panggil `artifact_loader.load_original_preprocessor`/`load_fitted_pipeline`. Docstring modul `_notebook_reference.py` diupdate (bukan lagi "TEST-ONLY" -- sekarang dipakai juga jalur produksi).

**Verifikasi:**
- `pytest tests/transform/test_parity_real_artifact.py -v` → **1 passed** (KK2 M1.2 tetap hijau persis seperti sebelum refactor -- SUPABASE_DB_URL tersedia, test benar-benar jalan bukan skip).
- `pytest tests/ -q` → **123 passed** (tidak ada import error dari pemindahan file).
- Smoke test manual `load_fitted_pipeline()` dipanggil berdiri sendiri (tanpa lewat test) pada 1 baris fixture (id=0, `notebook-audit.md` H.2) → `(1, 29)` shape, `tc_residual` ada -- bukti fungsi produksi bekerja independen dari harness test.

**File disentuh:** `src/churn_prediction/transform/_notebook_reference.py` (dipindah dari `tests/transform/`), `src/churn_prediction/transform/artifact_loader.py` (baru), `tests/transform/test_parity_real_artifact.py` (refactor, -47 baris duplikasi).

## Checkpoint 2 — Bundle pyfunc + registrasi versi 1

Dibuat `inference/pyfunc_model.py` (`ChurnPyfuncModel`) dan `inference/registry.py` (`build_bundle`, `register_model`, `load_model_by_version`).

**Temuan signifikan (dicatat sebagai Keputusan #9 di `decisions.md`, update juga di `docs/keputusan-tertunda.md` KT-3):** `joblib.load('artifacs/model/model_final.joblib')` gagal `ModuleNotFoundError: No module named 'lightgbm'` -- ini panggilan PERTAMA di seluruh proyek yang benar-benar memuat model (M1.2-1.4 cuma pernah memuat `preprocessor.joblib`). Diperiksa: `model_final.joblib` adalah `VotingClassifier` dengan `named_estimators_` = `lightgbm_class_weight`, `xgboost_class_weight`, `xgboost_smote` -- konsisten `notebook-audit.md` Bagian E (baseline+tuning notebook memang pakai XGBoost+LightGBM+RandomForest). Diinstal `lightgbm==4.7.0`+`xgboost==3.4.0`, ditambahkan ke `pyproject.toml` sebagai PROVISIONAL (pola sama pandas/numpy M1.2). Beda dari kasus scikit-learn (M1.2), tidak ada `InconsistentVersionWarning` bernomor versi eksplisit -- cuma `UserWarning` generik xgboost yang mengonfirmasi ADA mismatch versi tanpa menyebut versi persis. Diverifikasi manual: `predict_proba()` tetap menghasilkan output valid (non-NaN, `[[0.9455, 0.0545]]` untuk baris id=0) meski warning muncul -- aman dipakai.

**Verifikasi:**
- `pytest tests/inference/test_pyfunc_model.py -v` → **2 passed**: (1) `predict()` mengembalikan kolom `churn_probability`+`churn_label` sesuai threshold DARI BUNDLE; (2) dua bundle dengan threshold berbeda (0.9999 vs 0.0001) pada model+input SAMA menghasilkan probability identik tapi label total berbeda (0 vs 4 dari 4 baris) -- bukti threshold benar-benar dibaca dari bundle, bukan hardcode.
- `pytest tests/inference/test_registry.py -v` → **2 passed**: `build_bundle()` mengembalikan struktur benar; round-trip `register_model()`→`load_model_by_version("1")`→`predict()` pada tracking URI SQLite terisolasi (`tmp_path`, bukan `mlruns.db` bersama -- supaya nomor versi antar test run bisa diprediksi) menghasilkan versi "1" dan prediksi konsisten dengan threshold 0.6238.
- `pytest tests/ -q` → **127 passed**.

**File disentuh:** `src/churn_prediction/inference/{pyfunc_model,registry}.py` (baru), `tests/inference/{test_pyfunc_model,test_registry}.py` (baru), `pyproject.toml` (tambah lightgbm/xgboost), `milestones/1.5-inference-service/decisions.md` (Keputusan #9), `docs/keputusan-tertunda.md` (update KT-3).

## Checkpoint 3 — Versi 2 (uji) + bukti KK3 (load-by-version)

`registry.load_model_by_version()` sudah ada sejak Checkpoint 2 (dipakai Task 3). Checkpoint ini menambah `test_load_by_version_returns_version_appropriate_results` di `test_registry.py` -- bukti utama KK3.

**Mencari baris uji yang bermakna:** dicoba 500 baris real `telco_customers_source` (Supabase) lewat `registry.build_bundle()` -- dicari baris yang probability-nya jatuh di ANTARA threshold versi 2 uji (0.5) dan versi 1 (0.6238), supaya perbedaan threshold benar-benar menghasilkan `churn_label` berbeda (bukan cuma diasumsikan). Ditemukan 37 baris dalam band tersebut dari 500; dipilih `id=2` (probability 0.566305) sebagai fixture tetap (di-hardcode di test, bukan query live Supabase -- konsisten pola unit test lain yang hermetic/offline).

Test: registrasi bundle sungguhan (threshold 0.6238) sebagai versi 1, bundle uji (model SAMA, threshold 0.5) sebagai versi 2, keduanya ke tracking URI SQLite terisolasi yang SAMA dalam satu test. `load_model_by_version("1")` dan `load_model_by_version("2")` dipanggil pada baris id=2 yang sama.

**Verifikasi:**
- `pytest tests/inference/test_registry.py -v` → **3 passed**. Hasil KK3: `churn_probability` versi 1 == versi 2 (`pytest.approx`, model identik) TAPI `churn_label` versi 1 = 0 (0.566 < 0.6238) sedangkan versi 2 = 1 (0.566 >= 0.5) -- pembuktian langsung bahwa `load_model_by_version()` mengambil versi yang benar-benar diminta, bukan cache/selalu-versi-terakhir.
- `pytest tests/ -q` → **128 passed**.

**File disentuh:** `tests/inference/test_registry.py` (tambah 1 test + fixture `_band_row_df`).

## Checkpoint 4 — predict() publik + validasi skema

Dibuat `inference/predictor.py` -- `predict(df, model_version, tracking_uri=None)`. Validasi `RawDataSchema.validate(df)` dijalankan DI DALAM fungsi (Keputusan #4) sebelum `registry.load_model_by_version()` dipanggil sama sekali.

**Verifikasi (`tests/inference/test_predictor.py`, 7 test):**
- Input valid → DataFrame 4 kolom persis (`churn_probability`, `churn_label`, `model_version`, `predicted_at`), `predicted_at` berhasil di-parse balik sebagai timestamp ISO8601.
- Input invalid (`tenure=200`, `tenure=0`, `monthly_charges=-5.0`, `senior_citizen=2`, `contract="Weekly"`, kolom `tenure` hilang -- 6 kasus pelanggaran berbeda) → seluruhnya raise `pandera.errors.SchemaError`/`SchemaErrors` SEBELUM `registry.load_model_by_version()` sempat dipanggil sama sekali -- dibuktikan lewat `unittest.mock.patch.object` + `spy_load.assert_not_called()` (pola sama M1.4 `test_schema_transform_integration.py`), bukan cuma diasumsikan dari urutan baris kode.

`pytest tests/ -q` → **135 passed**.

**File disentuh:** `src/churn_prediction/inference/predictor.py` (baru), `tests/inference/test_predictor.py` (baru).

## Checkpoint 5 — Verifikasi KK1 (venv terpisah) + KK2 (parity end-to-end)

### KK2 (dikerjakan lebih dulu): parity end-to-end vs ground truth notebook asli

Dibuat `tests/inference/test_e2e_parity.py`, perluasan langsung M1.2 Checkpoint 5: ground truth = `preprocessor.joblib`+`model_final.joblib` asli dimuat LANGSUNG (`load_original_preprocessor` + `joblib.load`, TANPA bundle/MLflow sama sekali) → `predict_proba()[:,1]` → threshold 0.6238 manual. Dibandingkan terhadap `predictor.predict()` (lewat bundle+MLflow) pada 1000 baris real `telco_customers_source` (Supabase), termasuk wajib baris id=0,1,2.

**Verifikasi:** `pytest tests/inference/test_e2e_parity.py -v` → **1 passed** — `churn_probability` `np.allclose` (rtol 1e-6) DAN `churn_label` identik 100% dari 1000 baris. Bukti utama KK2: jalur penuh (validasi->transform->predict_proba->threshold->lineage) lewat package publik menghasilkan angka identik dengan ground truth notebook asli.

### KK1: instalasi & pemanggilan dari venv terpisah

**Temuan signifikan kedua (Keputusan #10):** percobaan pertama gagal -- venv baru (dibuat bersih via `python -m venv`, `pip install <path-repo>` TANPA `-e`, dari `pyproject.toml`) berhasil install, tapi `predict()` gagal `mlflow.tracking.registry.UnsupportedModelRegistryStoreURIException` untuk skema `sqlite:///`. Diagnosis: `mlflow-skinny` (Keputusan #8) TIDAK mendeklarasikan `sqlalchemy`/`alembic` sebagai dependency-nya sendiri, padahal keduanya wajib ada supaya mlflow bisa resolve backend `sqlite://`. Venv pengembangan tidak pernah menunjukkan masalah ini karena masih menyimpan `sqlalchemy`/`alembic` sebagai SISA instalasi `mlflow` penuh sebelum diganti `mlflow-skinny` di Checkpoint 0 -- `pip uninstall mlflow` tidak ikut membersihkan dependency transitifnya. Ini justru pembuktian langsung kenapa KK1 (venv benar-benar terpisah) adalah gerbang wajib, bukan opsional.

**Perbaikan + verifikasi ulang dari nol:** tambah `sqlalchemy==2.0.52`+`alembic==1.19.1` ke `pyproject.toml`. Dibuat venv KEDUA yang benar-benar bersih (tanpa instalasi manual apa pun di luar `pip install <repo>`), diregistrasi 1 bundle dari venv pengembangan ke tracking store SQLite terpisah (path absolut), lalu dari venv bersih tsb: `import churn_prediction.inference.predictor; predict(df_2_baris, model_version="1")` — BERHASIL, mengembalikan `churn_probability`/`churn_label`/`model_version`/`predicted_at` untuk kedua baris, tanpa satu baris kode `src/` pun diubah untuk venv kedua ini. Venv verifikasi (keduanya) dan file `mlruns_test.db` sementara dihapus setelah selesai (bukan bagian repo, tidak permanen).

`pytest tests/ -q` (venv pengembangan, setelah `pyproject.toml` diperbaiki) → **136 passed**.

**File disentuh:** `pyproject.toml` (tambah `sqlalchemy`+`alembic`), `tests/inference/test_e2e_parity.py` (baru), `milestones/1.5-inference-service/decisions.md` (Keputusan #10). Tidak ada file permanen dari verifikasi venv terpisah (sesuai plan).

## Checkpoint 6 (final) — Dokumentasi + Penutupan Milestone

Ditulis docstring lengkap `inference/__init__.py`: instalasi, kontrak `predict()` (tabel 4 kolom output), contoh pemanggilan, catatan eksplisit MLflow lokal/uji-M1.5 vs registrasi resmi M2.1, cara pakai `registry.build_bundle()`/`register_model()` untuk registrasi versi baru. `predict` di-re-export di level package (`from churn_prediction.inference import predict`) -- diverifikasi tidak ada circular import.

Dependency `pyproject.toml` sudah terkunci ke versi eksak sepanjang Checkpoint 0-5 (bukan ditunda ke sini) -- setiap versi (`mlflow-skinny`, `lightgbm`, `xgboost`, `sqlalchemy`, `alembic`) sudah dipin persis versi yang TERBUKTI jalan (diverifikasi ulang lewat 2 venv terpisah di Checkpoint 5), jadi tidak ada pin tertunda yang perlu diselesaikan di checkpoint ini.

`report.md` ditulis memetakan KK1-KK3 ke bukti Checkpoint 5, mencatat 10 keputusan total (6 klarifikasi + 4 turunan dari temuan teknis), keterbatasan (MLflow lokal-only, KT-3 belum tertutup untuk lightgbm/xgboost), dan follow-up untuk M2.1.

**Verifikasi akhir:** `pytest tests/ -q` → seluruh test suite tetap hijau.

**Penutupan Milestone 1.5:** package `churn_prediction.inference` selesai -- `predict(df, model_version) -> DataFrame` terverifikasi KK1 (2x venv terpisah, gap `sqlalchemy`/`alembic` ditemukan+diperbaiki), KK2 (parity end-to-end 1000 baris Supabase, probability+label identik), KK3 (load-by-version version-aware, 2 versi berbeda menghasilkan hasil berbeda sesuai versi). Push ke GitHub belum dilakukan, menunggu instruksi eksplisit user sesuai `CLAUDE.md`.

**File disentuh:** `src/churn_prediction/inference/__init__.py` (docstring lengkap), `milestones/1.5-inference-service/report.md` (baru).
