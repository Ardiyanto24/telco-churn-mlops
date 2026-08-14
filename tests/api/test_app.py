"""Test API real-time -- Milestone 3.2. `TestClient` (fastapi.testclient)
terhadap app FastAPI. Golden path pakai registry MLflow PRODUKSI sungguhan
(kredensial `.env`, pola sama `tests/inference/test_predictor.py`, ditandai
`integration`) -- kasus request tidak valid/startup gagal SENGAJA memakai
mock supaya tidak butuh kredensial/network (pola sama
`test_invalid_data_rejected_before_registry_called`), dibuktikan ULANG
secara nyata via container sungguhan (lihat
milestones/3.2-real-time-inference-api/logs.md Checkpoint 2).
"""

import asyncio
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from churn_prediction.api import app as app_module
from churn_prediction.api.app import LoadedModel, app
from churn_prediction.inference import registry


def _valid_payload(**overrides):
    payload = {
        "gender": "Male",
        "senior_citizen": 0,
        "partner": "Yes",
        "dependents": "No",
        "tenure": 29,
        "phone_service": "Yes",
        "multiple_lines": "No",
        "internet_service": "DSL",
        "online_security": "Yes",
        "online_backup": "No",
        "device_protection": "Yes",
        "tech_support": "Yes",
        "streaming_tv": "No",
        "streaming_movies": "No",
        "contract": "One year",
        "paperless_billing": "Yes",
        "payment_method": "Mailed check",
        "monthly_charges": 60.10,
        "total_charges": 1653.85,
    }
    payload.update(overrides)
    return payload


@pytest.mark.integration
def test_predict_valid_request_returns_full_contract():
    with TestClient(app) as client:
        response = client.post("/predict", json=_valid_payload())

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"churn_probability", "churn_label", "model_version", "predicted_at"}
    assert 0.0 <= body["churn_probability"] <= 1.0
    assert body["churn_label"] in (0, 1)
    assert body["model_version"]
    pd.Timestamp(body["predicted_at"])  # harus ISO8601 valid, raise kalau tidak


@pytest.mark.parametrize(
    "override",
    [
        {"tenure": 200},  # di luar rentang [1,72]
        {"monthly_charges": -5.0},  # harus > 0
        {"senior_citizen": 2},  # cuma {0,1}
        {"contract": "Weekly"},  # kategori tak dikenal
        {"tenure": "abc"},  # tipe salah
    ],
)
def test_predict_invalid_request_rejected_422_before_model_called(override):
    payload = _valid_payload(**override)
    with (
        patch.object(registry, "load_active_model", return_value=object()),
        patch.object(registry, "resolve_alias_version", return_value="1"),
        patch.object(app_module, "predict_active") as spy_predict,
    ):
        with TestClient(app) as client:
            response = client.post("/predict", json=payload)

    assert response.status_code == 422
    # request tidak valid ditolak FastAPI/Pydantic SEBELUM handler dijalankan
    # -- predict_active() (jadi model) tidak pernah dipanggil sama sekali.
    spy_predict.assert_not_called()


def test_predict_missing_field_rejected_422():
    payload = _valid_payload()
    del payload["tenure"]
    with (
        patch.object(registry, "load_active_model", return_value=object()),
        patch.object(registry, "resolve_alias_version", return_value="1"),
        patch.object(app_module, "predict_active") as spy_predict,
    ):
        with TestClient(app) as client:
            response = client.post("/predict", json=payload)

    assert response.status_code == 422
    spy_predict.assert_not_called()


def test_predict_returns_503_when_model_fails_to_load_at_startup():
    with patch.object(registry, "resolve_alias_version", side_effect=RuntimeError("registry unreachable")):
        with TestClient(app) as client:
            response = client.post("/predict", json=_valid_payload())

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "model_unavailable"
    assert "registry unreachable" in body["error"]["message"]


# ── /healthz (liveness) dan /readyz (readiness) -- Milestone 3.3 ───────────


def test_healthz_always_ok_even_when_model_fails_to_load():
    """Liveness TIDAK boleh terpengaruh status model -- kalau tidak, pod
    dengan model gagal dimuat akan di-restart terus-menerus oleh Kubernetes
    tanpa pernah membantu (lihat decisions.md Keputusan #3)."""
    with patch.object(registry, "resolve_alias_version", side_effect=RuntimeError("registry unreachable")):
        with TestClient(app) as client:
            response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
def test_readyz_200_when_model_loaded():
    with TestClient(app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["model_version"]


def test_readyz_503_when_model_fails_to_load():
    with patch.object(registry, "resolve_alias_version", side_effect=RuntimeError("registry unreachable")):
        with TestClient(app) as client:
            response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "model_unavailable"
    assert "registry unreachable" in body["error"]["message"]


# ── _refresh_once() -- Milestone 3.4 (deteksi versi tanpa restart) ─────────
# Diuji LANGSUNG (bukan lewat TestClient/asyncio.sleep) supaya tidak perlu
# menunggu interval polling sungguhan -- lihat decisions.md Keputusan #3.


def test_refresh_once_reloads_when_version_changed():
    app.state.loaded = LoadedModel(model="old-model-obj", model_version="1", load_error=None)
    with (
        patch.object(registry, "resolve_alias_version", return_value="2"),
        patch.object(registry, "load_active_model", return_value="new-model-obj") as spy_load,
    ):
        asyncio.run(app_module._refresh_once(app))

    spy_load.assert_called_once()
    assert app.state.loaded.model == "new-model-obj"
    assert app.state.loaded.model_version == "2"


def test_refresh_once_skips_reload_when_version_unchanged():
    app.state.loaded = LoadedModel(model="same-model-obj", model_version="1", load_error=None)
    with (
        patch.object(registry, "resolve_alias_version", return_value="1"),
        patch.object(registry, "load_active_model") as spy_load,
    ):
        asyncio.run(app_module._refresh_once(app))

    # versi sama -> load_active_model TIDAK dipanggil (hemat fetch S3).
    spy_load.assert_not_called()
    assert app.state.loaded.model == "same-model-obj"


def test_refresh_once_keeps_existing_model_when_refresh_fails():
    app.state.loaded = LoadedModel(model="good-model-obj", model_version="1", load_error=None)
    with patch.object(registry, "resolve_alias_version", side_effect=RuntimeError("registry unreachable")):
        asyncio.run(app_module._refresh_once(app))

    # model lama TETAP dipakai -- TIDAK di-downgrade ke None.
    assert app.state.loaded.model == "good-model-obj"
    assert app.state.loaded.model_version == "1"


def test_refresh_once_sets_error_when_first_load_fails():
    app.state.loaded = LoadedModel(model=None, model_version=None, load_error=None)
    with patch.object(registry, "resolve_alias_version", side_effect=RuntimeError("registry unreachable")):
        asyncio.run(app_module._refresh_once(app))

    # belum pernah ada model sukses -> perilaku M3.2 dipertahankan (model=None+error).
    assert app.state.loaded.model is None
    assert "registry unreachable" in app.state.loaded.load_error


# ── /metrics -- Milestone 3.5 (instrumentasi metrik infra API) ─────────────


def test_metrics_endpoint_exposes_prometheus_format():
    with TestClient(app) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_request_duration_seconds" in response.text


def test_metrics_reflects_real_request_counts_by_status_code():
    """KK1 M3.5 minta error rate/latency bisa dijawab dari metrik -- ini
    membuktikan counter/histogram BENAR-BENAR naik sesuai trafik nyata yang
    dikirim, bukan cuma endpoint /metrics ada.

    Dibandingkan lewat DELTA (bukan nilai absolut) -- REGISTRY prometheus_client
    bersifat global sepanjang proses pytest, counter dari test lain yang juga
    memanggil /predict (mis. test 422 di atas) ikut terakumulasi di sana."""
    from prometheus_client import REGISTRY

    def _count(status: str) -> float:
        return (
            REGISTRY.get_sample_value(
                "http_requests_total",
                {"handler": "/predict", "method": "POST", "status": status},
            )
            or 0.0
        )

    before_2xx, before_4xx = _count("2xx"), _count("4xx")

    with (
        patch.object(registry, "resolve_alias_version", return_value="1"),
        patch.object(registry, "load_active_model", return_value=object()),
        patch.object(app_module, "predict_active") as mocked_predict,
    ):
        mocked_predict.return_value = pd.DataFrame(
            [
                {
                    "churn_probability": 0.42,
                    "churn_label": 0,
                    "model_version": "1",
                    "predicted_at": "2026-08-14T00:00:00Z",
                }
            ]
        )
        with TestClient(app) as client:
            client.post("/predict", json=_valid_payload())  # 200
            client.post("/predict", json=_valid_payload(tenure=200))  # 422
            client.post("/predict", json=_valid_payload(tenure=200))  # 422 lagi

    assert _count("2xx") - before_2xx == 1.0
    assert _count("4xx") - before_4xx == 2.0
