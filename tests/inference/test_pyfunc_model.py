"""Unit test ``ChurnPyfuncModel`` -- Milestone 1.5 Checkpoint 2.

Menguji class pyfunc LANGSUNG (``load_context``+``predict``) lewat context
tiruan (duck-typed, cuma butuh atribut ``.artifacts``) -- tidak lewat
``mlflow.pyfunc.log_model``/registry sungguhan (itu Checkpoint 3,
``test_registry.py``). Memakai artifact ASLI (preprocessor ter-graft +
model_final.joblib) supaya angka yang dihasilkan bermakna, bukan model dummy.

Skip otomatis kalau ``artifacs/`` (model+preprocessor asli) tidak ada.
"""

from pathlib import Path

import joblib
import pandas as pd
import pytest

from churn_prediction.inference.pyfunc_model import ChurnPyfuncModel
from churn_prediction.transform.artifact_loader import (
    DEFAULT_PREPROCESSOR_PATH,
    load_fitted_pipeline,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = REPO_ROOT / "artifacs" / "model" / "model_final.joblib"

pytestmark = pytest.mark.skipif(
    not MODEL_PATH.exists() or not DEFAULT_PREPROCESSOR_PATH.exists(),
    reason="butuh artifacs/model/model_final.joblib dan artifacs/proprocessor/preprocessor.joblib",
)


class _FakeContext:
    """Duck-typed pengganti ``mlflow.pyfunc.model.PythonModelContext`` --
    ``ChurnPyfuncModel.load_context`` cuma memakai atribut ``.artifacts``."""

    def __init__(self, artifacts: dict):
        self.artifacts = artifacts


def _sample_raw_df():
    """4 baris, cakup semua kategori Contract/InternetService/PaymentMethod/
    tenure_group (pola sama tests/transform/test_pipeline.py)."""
    rows = [
        dict(
            gender="Male", senior_citizen=0, partner="Yes", dependents="No",
            tenure=1, phone_service="Yes", multiple_lines="No",
            internet_service="DSL", online_security="Yes", online_backup="No",
            device_protection="Yes", tech_support="No", streaming_tv="No", streaming_movies="No",
            contract="Month-to-month", paperless_billing="Yes",
            payment_method="Bank transfer (automatic)", monthly_charges=50.0, total_charges=50.0,
        ),
        dict(
            gender="Female", senior_citizen=1, partner="No", dependents="Yes",
            tenure=10, phone_service="No", multiple_lines="No phone service",
            internet_service="Fiber optic", online_security="No", online_backup="Yes",
            device_protection="No", tech_support="Yes", streaming_tv="Yes", streaming_movies="No",
            contract="One year", paperless_billing="No",
            payment_method="Credit card (automatic)", monthly_charges=80.0, total_charges=800.0,
        ),
        dict(
            gender="Male", senior_citizen=0, partner="Yes", dependents="Yes",
            tenure=30, phone_service="Yes", multiple_lines="Yes",
            internet_service="No", online_security="No internet service", online_backup="No internet service",
            device_protection="No internet service", tech_support="No internet service",
            streaming_tv="No internet service", streaming_movies="No internet service",
            contract="Two year", paperless_billing="Yes",
            payment_method="Electronic check", monthly_charges=20.0, total_charges=600.0,
        ),
        dict(
            gender="Female", senior_citizen=0, partner="No", dependents="No",
            tenure=60, phone_service="Yes", multiple_lines="No",
            internet_service="DSL", online_security="Yes", online_backup="Yes",
            device_protection="Yes", tech_support="Yes", streaming_tv="No", streaming_movies="Yes",
            contract="One year", paperless_billing="No",
            payment_method="Mailed check", monthly_charges=65.0, total_charges=3900.0,
        ),
    ]
    return pd.DataFrame(rows)


def _write_bundle(tmp_dir, threshold: float) -> Path:
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    pipeline = load_fitted_pipeline()
    model = joblib.load(MODEL_PATH)
    bundle_path = tmp_dir / "bundle.joblib"
    joblib.dump({"pipeline": pipeline, "model": model, "threshold": threshold}, bundle_path)
    return bundle_path


def test_predict_returns_probability_and_label_columns(tmp_path):
    bundle_path = _write_bundle(tmp_path, threshold=0.6238)
    pyfunc = ChurnPyfuncModel()
    pyfunc.load_context(_FakeContext({"bundle": str(bundle_path)}))

    df = _sample_raw_df()
    out = pyfunc.predict(context=None, model_input=df)

    assert list(out.columns) == ["churn_probability", "churn_label"]
    assert len(out) == len(df)
    assert out["churn_probability"].between(0, 1).all()
    assert set(out["churn_label"].unique()).issubset({0, 1})
    # threshold diterapkan dari bundle, bukan hardcode -- churn_label harus
    # persis sama dengan (probability >= threshold).
    expected_labels = (out["churn_probability"] >= 0.6238).astype(int)
    assert (out["churn_label"] == expected_labels).all()


def test_different_threshold_in_bundle_changes_label(tmp_path):
    """Threshold disimpan di bundle (Keputusan #3/#5) -- bundle dengan
    threshold rendah menghasilkan lebih banyak/sama churn_label=1."""
    df = _sample_raw_df()

    bundle_high = _write_bundle(tmp_path / "high", threshold=0.9999)
    pyfunc_high = ChurnPyfuncModel()
    pyfunc_high.load_context(_FakeContext({"bundle": str(bundle_high)}))
    out_high = pyfunc_high.predict(context=None, model_input=df)

    bundle_low = _write_bundle(tmp_path / "low", threshold=0.0001)
    pyfunc_low = ChurnPyfuncModel()
    pyfunc_low.load_context(_FakeContext({"bundle": str(bundle_low)}))
    out_low = pyfunc_low.predict(context=None, model_input=df)

    # probability identik (model sama) -- cuma label yang beda karena threshold.
    assert (out_high["churn_probability"] == out_low["churn_probability"]).all()
    assert out_high["churn_label"].sum() <= out_low["churn_label"].sum()
    assert out_low["churn_label"].sum() == len(df)  # threshold ~0 -> semua churn
    assert out_high["churn_label"].sum() == 0  # threshold ~1 -> tidak ada yang churn
