"""Test API real-time -- Milestone 3.2. `TestClient` (fastapi.testclient)
terhadap app FastAPI. Golden path pakai registry MLflow PRODUKSI sungguhan
(kredensial `.env`, pola sama `tests/inference/test_predictor.py`, ditandai
`integration`) -- kasus request tidak valid/startup gagal SENGAJA memakai
mock supaya tidak butuh kredensial/network (pola sama
`test_invalid_data_rejected_before_registry_called`), dibuktikan ULANG
secara nyata via container sungguhan (lihat
milestones/3.2-real-time-inference-api/logs.md Checkpoint 2).
"""

from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from churn_prediction.api import app as app_module
from churn_prediction.api.app import app
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
