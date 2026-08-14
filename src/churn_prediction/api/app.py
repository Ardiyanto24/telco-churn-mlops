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

Model dimuat saat startup DAN di-refresh berkala (Milestone 3.4) --
``LoadedModel`` (dataclass immutable) disimpan di ``app.state.loaded``,
diteruskan ke ``predict_active(model=..., resolved_version=...)`` supaya
tidak fetch ulang artifact dari MLflow registry (Postgres+S3 Supabase) di
setiap panggilan HTTP (Keputusan #3 M3.2).

``_refresh_once()`` dipakai BERSAMA startup (sekali) dan background task
periodik (``_refresh_loop()``, Milestone 3.4) -- satu sumber kebenaran
"cek versi alias champion -> reload kalau beda -> simpan hasil"
(milestones/3.4-deteksi-versi-model-aktif/decisions.md Keputusan #3).
Kalau startup gagal memuat model, app TETAP hidup (``loaded.model=None``)
-- ``/predict`` membalas 503 terstruktur, bukan membiarkan proses crash
(Keputusan #5 M3.2). Kalau REFRESH BERKALA gagal (mis. registry sempat
tidak terjangkau) TAPI model lama masih ada, model lama TETAP dipakai --
TIDAK di-downgrade ke None (beda dari kegagalan startup pertama kali).

``app.state.loaded`` SELALU di-assign sebagai SATU OBJEK BARU (bukan
mutasi field satu-per-satu) -- CPython GIL menjamin assignment satu
reference atomik lintas thread (handler ``/predict`` sinkron dijalankan di
threadpool Starlette, background refresh jalan di event loop) sehingga
request manapun yang membaca ``state.loaded`` SEKALI di awal handler tidak
pernah melihat kombinasi ``model``/``model_version`` yang tidak konsisten
(mis. model baru tapi model_version lama) -- lihat
milestones/3.4-deteksi-versi-model-aktif/decisions.md Keputusan #2.

``registry.resolve_alias_version()``/``load_active_model()`` SINKRON
(blocking I/O Postgres+S3) -- dipanggil dari ``_refresh_once()`` (async)
lewat ``asyncio.to_thread()`` supaya tidak memblokir event loop selama
polling/reload (Keputusan #5 M3.4).

``/healthz`` (liveness) dan ``/readyz`` (readiness) -- Milestone 3.3, lihat
milestones/3.3-deployment-kubernetes/decisions.md Keputusan #3. Dipisah
SENGAJA: liveness gagal -> Kubernetes RESTART pod; readiness gagal ->
Kubernetes cuma keluarkan pod dari trafik Service (tidak restart). Kalau
digabung, pod dengan model gagal dimuat (mis. registry down, KK3 M3.2) akan
di-restart terus-menerus tanpa pernah membantu (restart tidak memperbaiki
dependency eksternal yang down) -- crash-loop tak berguna.
"""

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from churn_prediction.inference import registry
from churn_prediction.inference.constants import ACTIVE_ALIAS
from churn_prediction.inference.predictor import predict_active
from churn_prediction.schema.request_schema import ChurnPredictionRequest

logger = logging.getLogger(__name__)

# Tidak ada SLA formal (KT-5, docs/keputusan-tertunda.md) -- 30 detik dipilih
# cukup cepat untuk "rentang waktu yang wajar" (KK1 M3.4) tanpa boros query
# registry. Bisa diubah tanpa ubah kode (env var, pola sama MLFLOW_TRACKING_URI).
REFRESH_INTERVAL_SECONDS = float(os.environ.get("MODEL_REFRESH_INTERVAL_SECONDS", "30"))


@dataclass(frozen=True)
class LoadedModel:
    """Snapshot model+lineage yang di-swap ATOMIK (satu assignment
    ``app.state.loaded = LoadedModel(...)``) -- lihat docstring modul untuk
    alasan kenapa TIDAK boleh jadi 3 atribut terpisah. ``frozen=True``
    mencegah mutasi in-place yang bisa diam-diam mereintroduksi race
    condition ini di masa depan."""

    model: object
    model_version: Optional[str]
    load_error: Optional[str]


_EMPTY = LoadedModel(model=None, model_version=None, load_error=None)


async def _refresh_once(app: FastAPI, alias: str = ACTIVE_ALIAS) -> None:
    """Cek versi alias `champion`, reload model HANYA kalau berubah --
    dipanggil startup (sekali) DAN background task (berkala), satu sumber
    kebenaran (Keputusan #3 M3.4)."""
    current: LoadedModel = app.state.loaded

    try:
        resolved_version = await asyncio.to_thread(registry.resolve_alias_version, alias)
    except Exception as exc:  # noqa: BLE001 -- boundary refresh: jangan crash background task
        logger.warning("Gagal cek versi alias %r: %r", alias, exc)
        if current.model is None:
            app.state.loaded = LoadedModel(model=None, model_version=None, load_error=str(exc))
        # else: model lama masih ada -- PERTAHANKAN, jangan downgrade ke None.
        return

    if current.model is not None and current.model_version == resolved_version:
        return  # tidak ada perubahan -- skip reload (hemat fetch S3)

    logger.info(
        "Versi alias %r berubah/pertama kali (%r -> %r), reload model...",
        alias,
        current.model_version,
        resolved_version,
    )
    try:
        model = await asyncio.to_thread(registry.load_active_model, alias)
        app.state.loaded = LoadedModel(model=model, model_version=resolved_version, load_error=None)
        logger.info("Reload model alias %r selesai -> versi %r", alias, resolved_version)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal reload model alias %r ke versi %r: %r", alias, resolved_version, exc)
        if current.model is None:
            app.state.loaded = LoadedModel(model=None, model_version=None, load_error=str(exc))
        # else: reload gagal tapi model lama masih ada -- PERTAHANKAN.


async def _refresh_loop(app: FastAPI, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        await _refresh_once(app)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.loaded = _EMPTY
    await _refresh_once(app)  # initial load -- blocking sama seperti M3.2 (startupProbe M3.3 mengandalkan ini)
    task = asyncio.create_task(_refresh_loop(app, REFRESH_INTERVAL_SECONDS))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Churn Prediction Real-Time API", lifespan=lifespan)


def _error_envelope(code: str, message: str) -> dict:
    """Bentuk error konsisten untuk kegagalan model/internal (503/500) --
    BEDA dari 422 bawaan FastAPI/Pydantic untuk request tidak valid, yang
    sengaja dipakai apa adanya (Keputusan #7 M3.2)."""
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
    mengeluarkan pod dari trafik Service sampai kondisi ini berubah."""
    loaded: LoadedModel = request.app.state.loaded
    if loaded.model is None:
        return JSONResponse(
            status_code=503,
            content=_error_envelope("model_unavailable", f"Model belum termuat: {loaded.load_error}"),
        )
    return {"status": "ready", "model_version": loaded.model_version}


@app.post("/predict")
def predict(payload: ChurnPredictionRequest, request: Request):
    loaded: LoadedModel = request.app.state.loaded
    if loaded.model is None:
        return JSONResponse(
            status_code=503,
            content=_error_envelope("model_unavailable", f"Model belum termuat: {loaded.load_error}"),
        )

    df = pd.DataFrame([payload.model_dump()])
    try:
        result = predict_active(df, model=loaded.model, resolved_version=loaded.model_version)
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
