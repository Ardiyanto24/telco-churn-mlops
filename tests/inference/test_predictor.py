"""Unit test ``inference.predictor.predict()`` -- Milestone 1.5 Checkpoint 4.

Kasus valid butuh model teregistrasi (artifact asli) -- skip kalau
``artifacs/`` tidak ada. Kasus invalid TIDAK butuh MLflow sama sekali (harus
gagal SEBELUM registry dipanggil -- dibuktikan lewat spy, pola sama
``tests/test_schema_transform_integration.py`` Milestone 1.4) sehingga tetap
jalan tanpa artifact/registry.
"""

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pandera.errors
import pytest

from churn_prediction.inference import predictor, registry
from churn_prediction.transform.artifact_loader import DEFAULT_PREPROCESSOR_PATH


def _valid_row(**overrides):
    row = {
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
    row.update(overrides)
    return row


@pytest.mark.skipif(
    not registry.DEFAULT_MODEL_PATH.exists() or not DEFAULT_PREPROCESSOR_PATH.exists(),
    reason="butuh artifacs/model/model_final.joblib dan artifacs/proprocessor/preprocessor.joblib",
)
def test_predict_valid_input_returns_full_contract(tmp_path):
    tracking_uri = f"sqlite:///{tmp_path.as_posix()}/mlruns_test.db"
    bundle = registry.build_bundle()
    registry.register_model(bundle, tracking_uri=tracking_uri)

    df = pd.DataFrame([_valid_row()])
    out = predictor.predict(df, model_version="1", tracking_uri=tracking_uri)

    assert list(out.columns) == ["churn_probability", "churn_label", "model_version", "predicted_at"]
    assert len(out) == 1
    assert out["churn_probability"].between(0, 1).all()
    assert set(out["churn_label"].unique()).issubset({0, 1})
    assert out["model_version"].iloc[0] == "1"
    # predicted_at harus ISO8601 UTC yang bisa di-parse balik.
    pd.Timestamp(out["predicted_at"].iloc[0])


def test_invalid_data_rejected_before_registry_called():
    """Data yang gagal RawDataSchema TIDAK PERNAH sampai memanggil registry
    (skip MLflow sepenuhnya) -- dibuktikan pakai spy, bukan cuma diasumsikan
    dari urutan baris kode di predictor.py."""
    df = pd.DataFrame([_valid_row(tenure=200)])  # di luar rentang [1,72]

    with patch.object(registry, "load_model_by_version") as spy_load:
        with pytest.raises(pandera.errors.SchemaError, match="tenure"):
            predictor.predict(df, model_version="1")
        spy_load.assert_not_called()


@pytest.mark.parametrize(
    "override",
    [
        {"tenure": 0},  # di luar rentang [1,72]
        {"monthly_charges": -5.0},  # harus > 0
        {"senior_citizen": 2},  # cuma {0,1}
        {"contract": "Weekly"},  # kategori tak dikenal
    ],
)
def test_multiple_invalid_cases_all_rejected(override):
    df = pd.DataFrame([_valid_row(**override)])

    with patch.object(registry, "load_model_by_version") as spy_load:
        with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
            predictor.predict(df, model_version="1")
        spy_load.assert_not_called()


def test_missing_column_rejected():
    row = _valid_row()
    del row["tenure"]
    df = pd.DataFrame([row])

    with patch.object(registry, "load_model_by_version") as spy_load:
        with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
            predictor.predict(df, model_version="1")
        spy_load.assert_not_called()
