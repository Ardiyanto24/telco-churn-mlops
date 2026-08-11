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
