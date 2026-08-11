"""Unit test ``inference.registry`` -- Milestone 1.5 Checkpoint 2.

Tiap test memakai tracking URI SQLite terisolasi di ``tmp_path`` (bukan
``constants.DEFAULT_TRACKING_URI`` yang dipakai jalur "nyata" repo) --
supaya nomor versi yang diregistrasi (1, 2, ...) bisa diprediksi/diuji
ulang tanpa terganggu state dari run test sebelumnya.

Skip otomatis kalau artifact asli (`artifacs/`) tidak ada.
"""

from pathlib import Path

import pandas as pd
import pytest

from churn_prediction.inference import registry
from churn_prediction.transform.artifact_loader import DEFAULT_PREPROCESSOR_PATH

pytestmark = pytest.mark.skipif(
    not registry.DEFAULT_MODEL_PATH.exists() or not DEFAULT_PREPROCESSOR_PATH.exists(),
    reason="butuh artifacs/model/model_final.joblib dan artifacs/proprocessor/preprocessor.joblib",
)


def _sample_raw_df():
    return pd.DataFrame([
        dict(
            gender="Female", senior_citizen=0, partner="Yes", dependents="No",
            tenure=29, phone_service="Yes", multiple_lines="No",
            internet_service="DSL", online_security="Yes", online_backup="No",
            device_protection="No", tech_support="No", streaming_tv="No", streaming_movies="No",
            contract="One year", paperless_billing="Yes",
            payment_method="Mailed check", monthly_charges=60.10, total_charges=1653.85,
        ),
    ])


def _tracking_uri(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path.as_posix()}/mlruns_test.db"


def test_build_bundle_returns_pipeline_model_threshold():
    bundle = registry.build_bundle()
    assert set(bundle.keys()) == {"pipeline", "model", "threshold"}
    assert bundle["threshold"] == 0.6238
    assert hasattr(bundle["pipeline"], "transform")
    assert hasattr(bundle["model"], "predict_proba")


def test_register_and_load_roundtrip_version_1(tmp_path):
    tracking_uri = _tracking_uri(tmp_path)
    bundle = registry.build_bundle()

    info = registry.register_model(bundle, tracking_uri=tracking_uri)
    assert str(info.registered_model_version) == "1"

    loaded = registry.load_model_by_version("1", tracking_uri=tracking_uri)
    out = loaded.predict(_sample_raw_df())

    assert list(out.columns) == ["churn_probability", "churn_label"]
    assert out["churn_probability"].between(0, 1).all()
    expected_label = int(out["churn_probability"].iloc[0] >= 0.6238)
    assert out["churn_label"].iloc[0] == expected_label
