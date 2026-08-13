# Logs — Milestone 3.2: Real-Time Inference API

## Checkpoint 1 — Fondasi API

**`predict_active()` diperluas** (parameter opsional `model`/`resolved_version`) — verifikasi regresi:
```
pytest tests/ -q
184 passed, 294 warnings in 132.10s
```
0 modifikasi ekspektasi test existing.

**`src/churn_prediction/api/app.py` dibuat** — smoke import:
```
python -c "from churn_prediction.api.app import app; print([r.path for r in app.routes])"
['/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc', '/predict']
```

**`tests/api/test_app.py` (8 test) dijalankan**:
```
pytest tests/api/ -v
8 passed, 13 warnings in 18.27s
```
Termasuk golden path (`test_predict_valid_request_returns_full_contract`, `@pytest.mark.integration`, terhadap registry produksi sungguhan) dan 5 kasus 422 (spy `predict_active` TIDAK dipanggil) + 1 kasus 503 (mock startup gagal).

**Full suite ulang** (setelah tambah `tests/api/`):
```
pytest tests/ -q
192 passed, 307 warnings in 135.53s
```

**Commit:** `8d788ab` — `feat(milestone-3.2): checkpoint 1 - fondasi real-time inference API`

## Checkpoint 2 — KK1/KK3/KK4 nyata via container

**Build image #1** (`churn-inference:m3.2`, Dockerfile + CMD uvicorn): sukses.

**Run + parity check PERCOBAAN PERTAMA — GAGAL, bug ditemukan:**
```
docker run -d -p 8000:8000 --env-file .env --name churn-api-test churn-inference:m3.2
python scripts/api_parity_check.py --api-url http://localhost:8000 --limit 20
```
```
churn_probability allclose(rtol=1e-6): False (diff maksimum: 0.36063257249553904)
churn_label exact match: False
model_version match: True
KK1+KK4 FAIL: parity tidak cocok.
```

**Debug** — bandingkan `predict_active()` panggilan LANGSUNG (bukan lewat HTTP) untuk `customer_id=0` vs API:
```
predict_active() direct result: churn_probability=0.035786875677172474 (MATCH ground truth 0.0357868756771725)
API response:                   churn_probability=0.01744073242573974  (BEDA)
```
Payload API dan `df_features` panggilan langsung berisi NILAI identik — hipotesis: urutan kolom. Dikonfirmasi:
```
order 1 (SQL-like, tenure posisi 5):        predict_active() -> 0.035786875677172474 (BENAR)
order 2 (pydantic-like, tenure di akhir):   predict_active() -> 0.017440732425739743 (SALAH)
```
Root-cause lebih dalam — `pipeline.transform()` dua urutan input dibandingkan:
```
t1 columns (SQL order):      [...'phone_service'(pos4)...'paperless_billing'(pos12)...]
t2 columns (pydantic order): [...'phone_service'(pos3)...'paperless_billing'(pos4)...]
same column order: False
same values (aligned by name): True
```
Terbukti: `pipeline.transform()` benar secara NILAI per-nama-kolom, tapi urutan OUTPUT ikut urutan INPUT — root cause pasti (lihat `decisions.md` Keputusan #10).

**Fix diterapkan** (`src/churn_prediction/inference/pyfunc_model.py`) — reorder ke `RAW_PASCAL_TO_SNAKE.values()` sebelum `pipeline.transform()`.

**Verifikasi fix — LANGSUNG terhadap registry (tanpa rebuild image, tanpa re-registrasi model)**:
```
result (pydantic order, EXISTING registered champion v1): churn_probability=0.035786875677172474
expected (ground truth): 0.0357868756771725
```
MATCH — mengonfirmasi MLflow me-load ulang class dari package terinstal, bukan membekukan kode saat registrasi.

**Full suite ulang setelah fix:**
```
pytest tests/ -q
192 passed, 307 warnings in 125.32s
```
0 regresi.

**Rebuild image #2** (dengan fix) + run ulang:
```
docker build -t churn-inference:m3.2 .   # sukses
docker run -d -p 8000:8000 --env-file .env --name churn-api-test churn-inference:m3.2
```
Startup log:
```
WARNING mlflow.utils.requirements_utils: Detected one or more mismatches...
 - pyarrow (current: uninstalled, required: pyarrow==25.0.1)
Application startup complete.
```
(Warning non-fatal, pola sama versi mismatch M1.5 KT-3 — model tetap termuat+prediksi valid.)

**Parity check ULANG (limit=20):**
```
Versi champion aktif saat ini: 1
Ground truth: 20 baris (model_version=1)
churn_probability allclose(rtol=1e-6): True (diff maksimum: 4.440892098500626e-16)
churn_label exact match: True
model_version match: True
KK1+KK4 PASS: parity API real-time vs batch (M2.5) terbukti.
```

**Parity check skala lebih besar (limit=100), verifikasi tambahan:**
```
Ground truth: 100 baris (model_version=1)
churn_probability allclose(rtol=1e-6): True (diff maksimum: 4.996003610813204e-16)
churn_label exact match: True
model_version match: True
KK1+KK4 PASS: parity API real-time vs batch (M2.5) terbukti.
```

Container `churn-api-test` dihentikan+dihapus setelah verifikasi.

**Uji coba terkontrol KK3 — model gagal dimuat NYATA:**
```
docker run -d -p 8001:8000 --env-file .env \
  -e MLFLOW_TRACKING_URI="postgresql://invalid_user:wrong@host-tidak-ada.invalid:5432/postgres" \
  --name churn-api-broken churn-inference:m3.2
```
Log startup — retry backoff internal MLflow (`mlflow.store.db.utils`), exponensial (0.1s, 0.3s, 0.7s, 1.5s, 3.1s, 6.3s, 12.7s, 25.5s, 51.1s — total ~100 detik) sebelum akhirnya `Application startup complete` (lifespan menangkap exception, `app.state.model=None`) — proses TIDAK crash selama ini.

```
curl -X POST http://localhost:8001/predict -d '{...request valid...}'
HTTP_STATUS:503
{"error":{"code":"model_unavailable","message":"Model belum termuat: (psycopg2.OperationalError) could not translate host name \"host-tidak-ada.invalid\" to address: Name or service not known\n\n..."}}
```
KK3 terbukti nyata — 503 terstruktur, bukan crash/timeout/connection-refused. Container `churn-api-broken` dihentikan+dihapus setelah verifikasi.

**Commit:**
- `53b55a6` — `fix(inference): reorder DataFrame ke urutan kolom kanonik sebelum predict()`
- `d4dc8e9` — `feat(milestone-3.2): checkpoint 2 - container API + verifikasi parity KK1/KK3/KK4 nyata`
