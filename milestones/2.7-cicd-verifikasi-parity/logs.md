# Logs — Milestone 2.7: CI/CD dan Verifikasi Parity Otomatis

## Riset Sebelum Plan Ditulis

`gh run list --limit 10` menunjukkan SELURUH run historis `.github/workflows/test.yml` berstatus `failure` (dari M1.6 sampai commit terakhir M2.6). `gh run view <id> --log-failed` pada run terbaru: `ERROR: Could not find a version that satisfies the requirement numpy==2.5.2` — log detail menunjukkan versi 2.5.0/2.5.1 eksplisit "Requires-Python >=3.12", sementara `test.yml` mem-pin Python 3.11. `./.venv/Scripts/python.exe --version` lokal → `Python 3.13.12` (bukan 3.11). Root cause dikonfirmasi sebelum menulis plan.

## Checkpoint 1 — Perbaiki fondasi CI

**Task 1-3:** `test.yml` python-version → "3.13", install → `[dev,orchestration]`; `pyproject.toml` requires-python → ">=3.12"; `.env.example` dilengkapi 6 var yang hilang.

**Selesai, commit:** `9e85e92` (fix, milestone-1.4), `c9ec666` (docs).

**Task 4 (push + verifikasi, izin diminta & didapat):** Run pertama (`31667525767`) — instalasi numpy+prefect SUKSES (progress nyata), tapi step "Run test suite" gagal exit code 2: `ModuleNotFoundError: No module named 'orchestration'`. **Reproduksi lokal:** `pytest tests/orchestration/test_batch_scoring.py --collect-only -q` (bare `pytest`, BUKAN `python -m pytest`) menghasilkan error IDENTIK — bug nyata, bukan CI-specific. **Diagnosis:** bare `pytest` tidak menaruh root repo di `sys.path`, beda `python -m pytest` yang dipakai sepanjang sesi sebelumnya. **Fix:** `pyproject.toml` `[tool.pytest.ini_options] pythonpath = ["."]`. Verifikasi lokal: `pytest tests/ -q` (bare) → 170 passed. Commit `f585f1f` (fix, milestone-2.7), push, run kedua (`31667788959`) → **HIJAU** (pertama kalinya di seluruh sejarah proyek): `144 passed, 26 skipped, 1 warning`.

## Checkpoint 2 — Pisah gate unit-test vs integration/parity

**Task 5:** Grep pola `pytestmark.*skipif` menemukan 9 file. Diperiksa satu per satu — 6 file skip berdasarkan kredensial Supabase/MLflow (ditandai `integration`), 3 file (`test_registry.py`, `test_predictor.py`, `test_pyfunc_model.py`) skip berdasarkan `artifacs/` (gitignored) — SENGAJA TIDAK ditandai (lihat decisions.md Keputusan #4). Marker `integration` didaftarkan `pyproject.toml`.

**Verifikasi split lokal:** `pytest tests/ -m "not integration"` → 154 passed, 16 deselected. `pytest tests/ -m "integration"` → **2 ERROR** tak terduga (`test_batch_predictions_match_direct_predict_active_call`, `test_lineage_traces_back_to_real_mlflow_version`): `MlflowException('Registered model alias champion not found.')`.

**Investigasi bug MLflow (Task 6, sebelum lanjut):** Verifikasi langsung ke registry real (`client.get_model_version_by_alias`) → alias `champion` VERIFIED ada, versi 1, benar. Biseksi: `pytest tests/orchestration/test_batch_scoring.py -m integration` SENDIRIAN → 4 passed bersih. `pytest tests/inference/test_e2e_parity.py tests/orchestration/test_batch_scoring.py -m integration` (2 file) → reproduksi 2 error yang sama (minimal repro berhasil). **Repro standalone** (`repro_mlflow_uri_switch.py`): query alias real (OK) → register bundle ke tracking URI SQLite sementara → `tempfile.TemporaryDirectory.__exit__` GAGAL `PermissionError: [WinError 32] file digunakan proses lain` — BUKTI KONKRET MLflow client men-cache koneksi/engine per tracking-URI tanpa dispose. **Fix:** `integration-tests` job dipecah jadi 2 langkah `pytest` TERPISAH (proses baru masing-masing) — `tests/orchestration` lalu sisanya. Verifikasi ulang lokal: `pytest tests/orchestration -m integration` (4 passed) + `pytest tests/ --ignore=tests/orchestration -m integration` (12 passed) — SEMUA lolos sebagai 2 proses terpisah.

**Selesai, commit:** `76c193d` (feat, milestone-2.7 — marker + workflow split + fix MLflow cache).

**Task 7 (provisioning secret, izin diminta & didapat):** 10 secret di-set via `gh secret set` (nilai dari `.env`, tidak pernah dicetak). `gh secret list` mengonfirmasi 10 nama ter-set.

**Task 8 (push + verifikasi, run `31670275809`):** `unit-tests` PASS (144/10/16, konsisten). `integration-tests` step "orchestration" GAGAL: `ValueError: Invalid endpoint: ` (boto3, endpoint kosong) — **bug ke-4 ditemukan**: `MLFLOW_S3_ENDPOINT_URL` TERLEWAT dari daftar 10 secret (ternyata ADA di `.env` baris 20, terlewat saat menyusun daftar — kesalahan proses, dikonfirmasi lewat `grep -n` langsung). **Fix:** 1 secret tambahan di-set, `gh run rerun 31670275809 --failed` (tanpa commit baru). Run ulang → **SEMUA HIJAU**: `unit-tests` (144 passed, 10 skipped, 16 deselected), `integration-tests` step 1 (4 passed), step 2 (10 passed, 2 skipped [artifact-gated, expected], 154 deselected). **KD-1 TIDAK muncul** di GitHub Actions ubuntu-latest — model LightGBM dimuat sukses tanpa perlu `apt-get install libgomp1` (VM penuh, beda dari Prefect Managed).

**Task 9 (uji coba terkontrol Gate 1):** Branch `ci-test-broken-transform`, `BinaryEncoder.BINARY_MAP` dibalik (`{"Yes":0,"No":1}`), push. Run `31670969575`: `unit-tests` GAGAL (exit 1), `integration-tests` **TIDAK PERNAH JALAN** (0s, `needs:` menghentikan pipeline) — bukti KK1 sumber. Branch dihapus (lokal+remote), `main` bersih.

**Task 10 (uji coba terkontrol Gate 3):** Branch `ci-test-broken-parity`, `score_batch()` disisipi `features["tenure"] = 1` (menyimpang dari `predict_active()` bersih). Run `31671095111`: `integration-tests` step orchestration GAGAL — `FAILED tests/orchestration/test_batch_scoring.py::test_batch_predictions_match_direct_predict_active_call - AssertionError` (nilai churn_probability berbeda) — spesifik test parity, bukan sebab lain. Branch dihapus, `main` bersih.

## Checkpoint 3 — Gate 2: gerbang kualitas data otomatis, non-recording

**Task 11-12:** `run_gate()` (`gate.py`) dapat parameter `record_history: bool = True` — kalau `False`, `baseline_store.record_run()` TIDAK dipanggil, `run_id=None`. Dua test baru `tests/quality/test_gate.py`: `test_record_history_false_does_not_write_row` (verifikasi row count sebelum/sesudah TIDAK berubah), `test_record_history_true_default_still_writes_row` (default tetap menulis +1). Lokal: `pytest tests/quality/test_gate.py -v` → 7 passed (5 lama + 2 baru).

**Task 13:** `orchestration/ci_quality_check.py` ditulis. **Bug ditemukan+diperbaiki saat sanity check lokal:** skrip awal me-rename kolom ke snake_case SEBELUM memanggil `run_gate()` — salah, `run_gate()` di DAG M2.5 dipanggil dengan df PascalCase MENTAH (rename baru terjadi di `score_batch()`, setelahnya). `KeyError: 'MonthlyCharges'` muncul saat run lokal pertama. Diperbaiki (hapus rename), verifikasi ulang: `verdict=pass`, exit 0.

**Task 14:** Job `quality-data-check` (`needs: unit-tests`) ditambah ke `test.yml`.

**Selesai, commit:** `5d18621` (feat, milestone-2.7).

**Task 15 (push + verifikasi, run `31671748392`):** Row count `quality.gate_run_history WHERE source_table='telco_customers_source'` dicatat SEBELUM run: **0**. Ketiga job (`unit-tests`, `quality-data-check`, `integration-tests`) HIJAU. Row count dicek ULANG SETELAH run selesai: **0** (tidak berubah) — bukti konkret non-recording bekerja di CI sungguhan, bukan cuma lokal.

## Checkpoint 4 — Gate 4

**Task 16:** Komentar konvensi `needs: [unit-tests, quality-data-check, integration-tests]` sudah ditulis di `test.yml` sejak Checkpoint 2 (forward-looking), diverifikasi masih akurat sekarang seluruh job yang dirujuk benar-benar ada.

## Checkpoint 5 — Dokumentasi dan penutupan

**Task 17:** KT-7 ditulis ke `docs/keputusan-tertunda.md` (parity CI penuh vs real-time API sungguhan, menunggu M3.x).

**Verifikasi akhir (`pytest tests/ -q` lokal, bare):** **172 passed** (170 + 2 test `record_history` baru), 0 gagal, 0 error.

**Selesai, commit:** (dicatat di pesan commit git untuk hash final).
