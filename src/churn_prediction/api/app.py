"""Real-time inference API -- Milestone 3.2. Endpoint HTTP tunggal
(``POST /predict``) di atas ``churn_prediction.inference.predictor.predict_active()``
(Milestone 2.1/2.5), mengembalikan prediksi + lineage (versi model, waktu
prediksi) untuk satu pelanggan per panggilan.

Fitur HANYA diambil dari payload request -- TIDAK ada langkah "ambil dari
feature store". Milestone 2.2 sudah memutuskan final: seluruh 29 fitur model
berklasifikasi INSTANT, tidak ada feature store yang dibangun (lihat
milestones/2.2-klasifikasi-fitur-feature-store/decisions.md dan
milestones/3.2-real-time-inference-api/decisions.md Keputusan #2 untuk
deviasi terdokumentasi dari teks ``mlops-03-deployment-observability.md``).

Model dimuat SEKALI saat startup (``lifespan``), bukan per-request --
disimpan di ``app.state``, diteruskan ke ``predict_active(model=...,
resolved_version=...)`` supaya tidak fetch ulang artifact dari MLflow
registry (Postgres+S3 Supabase) di setiap panggilan HTTP (Keputusan #3).
Kalau startup gagal memuat model, app TETAP hidup (``app.state.model=None``)
-- ``/predict`` membalas 503 terstruktur, bukan membiarkan proses crash
(Keputusan #5) -- "restart untuk pick up versi model baru" adalah
keterbatasan SAH milestone ini, mekanisme refresh-tanpa-restart adalah
scope Milestone 3.4 (dijadwalkan terpisah).

``/healthz`` (liveness) dan ``/readyz`` (readiness) -- Milestone 3.3, lihat
milestones/3.3-deployment-kubernetes/decisions.md Keputusan #3. Dipisah
SENGAJA: liveness gagal -> Kubernetes RESTART pod; readiness gagal ->
Kubernetes cuma keluarkan pod dari trafik Service (tidak restart). Kalau
digabung, pod dengan model gagal dimuat (mis. registry down, KK3 M3.2) akan
di-restart terus-menerus tanpa pernah membantu (restart tidak memperbaiki
dependency eksternal yang down) -- crash-loop tak berguna.
"""

from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from churn_prediction.inference import registry
from churn_prediction.inference.constants import ACTIVE_ALIAS
from churn_prediction.inference.predictor import predict_active
from churn_prediction.schema.request_schema import ChurnPredictionRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.model_version = registry.resolve_alias_version(ACTIVE_ALIAS)
        app.state.model = registry.load_active_model(alias=ACTIVE_ALIAS)
        app.state.load_error = None
    except Exception as exc:  # noqa: BLE001 -- boundary startup: app HARUS tetap hidup (Keputusan #5)
        app.state.model = None
        app.state.model_version = None
        app.state.load_error = str(exc)
    yield


app = FastAPI(title="Churn Prediction Real-Time API", lifespan=lifespan)


def _error_envelope(code: str, message: str) -> dict:
    """Bentuk error konsisten untuk kegagalan model/internal (503/500) --
    BEDA dari 422 bawaan FastAPI/Pydantic untuk request tidak valid, yang
    sengaja dipakai apa adanya (Keputusan #7)."""
    return {"error": {"code": code, "message": message}}


@app.get("/healthz")
def healthz():
    """Liveness -- selalu 200 selama proses bisa merespons HTTP, TIDAK
    mengecek status model (lihat docstring modul di atas kenapa dipisah dari
    /readyz)."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz(request: Request):
    """Readiness -- mencerminkan kesiapan MODEL (KK2 Milestone 3.3), bukan
    cuma proses hidup. 503 kalau model belum/gagal dimuat -- Kubernetes
    mengeluarkan pod dari trafik Service sampai kondisi ini berubah (lewat
    restart manual, bukan retry otomatis -- lihat Keputusan #5 M3.2)."""
    state = request.app.state
    if state.model is None:
        return JSONResponse(
            status_code=503,
            content=_error_envelope("model_unavailable", f"Model belum termuat: {state.load_error}"),
        )
    return {"status": "ready", "model_version": state.model_version}


@app.post("/predict")
def predict(payload: ChurnPredictionRequest, request: Request):
    state = request.app.state
    if state.model is None:
        return JSONResponse(
            status_code=503,
            content=_error_envelope("model_unavailable", f"Model belum termuat: {state.load_error}"),
        )

    df = pd.DataFrame([payload.model_dump()])
    try:
        result = predict_active(df, model=state.model, resolved_version=state.model_version)
    except Exception as exc:  # noqa: BLE001 -- boundary request: jangan pernah menyamarkan kegagalan
        return JSONResponse(
            status_code=500,
            content=_error_envelope("internal_error", f"Kegagalan tak terduga saat prediksi: {exc!r}"),
        )

    row = result.iloc[0]
    return {
        "churn_probability": float(row["churn_probability"]),
        "churn_label": int(row["churn_label"]),
        "model_version": row["model_version"],
        "predicted_at": row["predicted_at"],
    }
