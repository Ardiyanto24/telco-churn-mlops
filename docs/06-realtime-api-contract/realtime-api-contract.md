# Kontrak Real-Time Inference API

Disepakati Milestone 3.2 (`milestones/3.2-real-time-inference-api/decisions.md`). Rujukan bagi siapa pun yang memanggil endpoint `/predict` — konsumen eksternal, tim lain, atau milestone lanjutan (M3.3 deployment, M3.5 monitoring).

Skema request adalah `ChurnPredictionRequest` (Milestone 1.3, `src/churn_prediction/schema/request_schema.py`) dipakai LANGSUNG oleh API — bukan skema baru. Dokumen ini merujuk, bukan mendefinisikan ulang.

Dokumentasi interaktif (OpenAPI/Swagger) otomatis tersedia di `GET /docs` selama service berjalan — dihasilkan FastAPI dari `ChurnPredictionRequest` yang sama, selalu sinkron dengan kode.

## 1. Endpoint

`POST /predict` — satu pelanggan per panggilan (lihat `decisions.md` Keputusan #4).

## 2. Skema Request

19 field snake_case, identik nama+tipe dengan kolom data mentah (`RawDataSchema`) — lihat `src/churn_prediction/schema/request_schema.py` untuk daftar lengkap+aturan validasi (kategori valid, rentang numerik). Ringkasan:

| Field | Tipe | Aturan |
|---|---|---|
| `gender` | str | `{"Female", "Male"}` |
| `senior_citizen` | int | `{0, 1}` |
| `partner`, `dependents`, `phone_service`, `paperless_billing` | str | `{"Yes", "No"}` |
| `multiple_lines` | str | `{"Yes", "No", "No phone service"}` |
| `internet_service` | str | `{"DSL", "Fiber optic", "No"}` |
| `online_security`, `online_backup`, `device_protection`, `tech_support`, `streaming_tv`, `streaming_movies` | str | `{"Yes", "No", "No internet service"}` |
| `contract` | str | `{"Month-to-month", "One year", "Two year"}` |
| `payment_method` | str | `{"Bank transfer (automatic)", "Credit card (automatic)", "Electronic check", "Mailed check"}` |
| `tenure` | int | `1 <= x <= 72` |
| `monthly_charges` | float | `> 0` |
| `total_charges` | float | `>= 0` |

Tidak ada field ID/correlation (lihat `decisions.md` Keputusan #8).

## 3. Skema Response — Sukses (200)

```json
{
  "churn_probability": 0.035786875677172474,
  "churn_label": 0,
  "model_version": "1",
  "predicted_at": "2026-08-13T22:36:43.309718+00:00"
}
```

| Field | Tipe | Keterangan |
|---|---|---|
| `churn_probability` | float | `model.predict_proba(X)[:, 1]` |
| `churn_label` | int (0/1) | `churn_probability >= threshold` (threshold tersimpan di bundle versi yang dimuat) |
| `model_version` | str | Nomor versi KONKRET model yang menghasilkan prediksi ini (bukan nama alias `champion`) |
| `predicted_at` | str | ISO8601 UTC — lineage minimal (Bagian 5.6 dokumen arsitektur) |

## 4. Skema Response — Error

**422 Unprocessable Entity** (request tidak valid — field hilang, tipe salah, di luar rentang/kategori) — bentuk BAWAAN FastAPI/Pydantic, tidak dikustomisasi (lihat `decisions.md` Keputusan #7):

```json
{
  "detail": [
    {"loc": ["body", "tenure"], "msg": "Input should be less than or equal to 72", "type": "less_than_equal"}
  ]
}
```

**503 Service Unavailable** (model belum/gagal dimuat dari MLflow registry — lihat `decisions.md` Keputusan #5):

```json
{"error": {"code": "model_unavailable", "message": "Model belum termuat: <detail exception>"}}
```

**500 Internal Server Error** (kegagalan tak terduga saat prediksi, setelah model termuat):

```json
{"error": {"code": "internal_error", "message": "Kegagalan tak terduga saat prediksi: <detail exception>"}}
```

## 5. Contoh Pemanggilan (`curl`)

**Golden path:**
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "gender": "Male", "senior_citizen": 0, "partner": "Yes", "dependents": "No",
    "tenure": 29, "phone_service": "Yes", "multiple_lines": "No",
    "internet_service": "DSL", "online_security": "Yes", "online_backup": "No",
    "device_protection": "Yes", "tech_support": "Yes", "streaming_tv": "No",
    "streaming_movies": "No", "contract": "One year", "paperless_billing": "Yes",
    "payment_method": "Mailed check", "monthly_charges": 60.10, "total_charges": 1653.85
  }'
```

**Request tidak valid** (`tenure` di luar rentang `[1, 72]`) → 422:
```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" \
  -d '{"...": "...", "tenure": 200}'
```

**Model tidak tersedia** (uji coba terkontrol — jalankan container dengan `MLFLOW_TRACKING_URI` rusak) → 503:
```bash
docker run -d -p 8000:8000 --env-file .env \
  -e MLFLOW_TRACKING_URI=postgresql://invalid-host/postgres \
  churn-inference:m3.2
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" -d '{...}'
```

## 6. Yang TIDAK Dicakup Kontrak Ini

- **Feature store**: TIDAK ADA — seluruh fitur diambil dari payload request (Milestone 2.2, lihat `milestones/3.2-real-time-inference-api/decisions.md` Keputusan #2 untuk deviasi terdokumentasi dari teks `mlops-03-deployment-observability.md`).
- **`/health`/readiness formal**: belum dibangun — wewenang Milestone 3.3 (lihat `decisions.md` Keputusan #6).
- **Refresh versi model tanpa restart**: belum dibangun — wewenang Milestone 3.4. Promosi/rollback alias `champion` di registry baru diikuti API ini setelah RESTART container.
- **Batch/array request**: tidak didukung — satu entity per panggilan (Keputusan #4).
