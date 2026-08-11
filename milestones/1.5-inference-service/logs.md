# Logs — Milestone 1.5: Inference Service Package

## Checkpoint 0 — Keputusan + scaffold

**Mulai:** 2026-08-11.

**Klarifikasi sebelum plan:** 5 pertanyaan diajukan lewat AskUserQuestion (MLflow lokal vs server, registrasi resmi model_final.joblib sekarang vs M2.1, kontrak output, kontrak input, bundling preprocessor+model) — semua dijawab user sebelum plan ditulis. Detail lengkap di `decisions.md`.

**Temuan Task 0b (scaffold dependency) — dua penyimpangan dari asumsi awal plan, keduanya diverifikasi konkret sebelum diputuskan, dicatat sebagai Keputusan #7 dan #8 di `decisions.md`:**

1. `pip install mlflow` (paket penuh) menarik `pandas<3` sebagai dependency-nya sendiri dan **mendowngrade pandas dari 3.0.5 (terkunci M1.2) ke 2.3.3** secara otomatis. Ini konflik langsung dengan dependency yang sudah dikunci berdasarkan environment TERBUKTI jalan dengan `preprocessor.joblib` asli DS. Diverifikasi: `mlflow-skinny` (variant client-only) TIDAK punya dependency ke pandas/numpy/scikit-learn sama sekali (`importlib.metadata.requires('mlflow-skinny')` — list kosong untuk ketiganya). Uninstall `mlflow` penuh, reinstall `pandas==3.0.5`, konfirmasi `mlflow-skinny` tetap menyediakan `mlflow.pyfunc.PythonModel`/`log_model`/`register_model`/`load_model` (seluruh API yang dipakai M1.5 karena kita pakai custom pyfunc, bukan flavor `mlflow.sklearn`). Diputuskan: pakai `mlflow-skinny==3.15.1`, bukan `mlflow`.

2. Percobaan awal `mlflow.set_tracking_uri("file:./mlruns")` (URI literal yang disebut di plan Keputusan #1) gagal dengan `MlflowException`: filesystem tracking backend murni sudah masuk **maintenance mode** di mlflow 3.15.1 ("will not receive further updates ... set MLFLOW_ALLOW_FILE_STORE=true to opt out"). Smoke test dengan `sqlite:///mlruns.db` (backend lokal alternatif, tetap tanpa server) berhasil penuh: register 2 versi model, keduanya berhasil dimuat independen lewat `models:/<name>/<version>`. Diputuskan: `DEFAULT_TRACKING_URI = "sqlite:///mlruns.db"`, bukan `file:./mlruns`.

**Verifikasi:** `pytest tests/ -q` → **123 passed** (termasuk `test_kk2_parity_against_real_artifact_on_supabase_data` yang benar-benar JALAN, bukan skip — `SUPABASE_DB_URL` tersedia di environment ini via `.env`). Membuktikan penambahan `mlflow-skinny` tidak mengganggu dependency M1.2-1.4 yang sudah terkunci.

**File disentuh:** `pyproject.toml` (tambah `mlflow-skinny==3.15.1`), `.gitignore` (tambah `mlruns/`, `mlruns.db`), `.env.example` (tambah `MLFLOW_TRACKING_URI`), `src/churn_prediction/inference/{__init__,constants}.py` (skeleton), `milestones/1.5-inference-service/decisions.md`.
