"""Unit test ``inference.artifact_validation.sanity_check_bundle()`` --
Milestone 2.8 Checkpoint 1.

Kasus bundle RUSAK memakai fake pipeline/model (TIDAK butuh artifact asli --
selalu jalan). Kasus bundle VALID butuh ``build_bundle()`` sungguhan (skip
kalau ``artifacs/`` tidak ada, pola sama file test lain di direktori ini).
"""

import numpy as np
import pandas as pd
import pytest

from churn_prediction.inference import registry
from churn_prediction.inference.artifact_validation import sanity_check_bundle
from churn_prediction.transform.artifact_loader import DEFAULT_PREPROCESSOR_PATH


class _IdentityPipeline:
    def transform(self, X):
        return X


class _NaNModel:
    """Fake model -- predict_proba() SENGAJA mengembalikan NaN, mensimulasikan
    artifact rusak tanpa perlu file asli."""

    def predict_proba(self, X):
        n = len(X)
        out = np.full((n, 2), np.nan)
        return out


class _OutOfRangeModel:
    """Fake model -- predict_proba() mengembalikan nilai di luar [0,1]."""

    def predict_proba(self, X):
        n = len(X)
        return np.full((n, 2), 5.0)


class _CrashingPipeline:
    def transform(self, X):
        raise RuntimeError("preprocessing sengaja gagal (uji coba terkontrol)")


@pytest.mark.skipif(
    not registry.DEFAULT_MODEL_PATH.exists() or not DEFAULT_PREPROCESSOR_PATH.exists(),
    reason="butuh artifacs/model/model_final.joblib dan artifacs/proprocessor/preprocessor.joblib",
)
def test_valid_bundle_passes_sanity_check():
    bundle = registry.build_bundle()
    result = sanity_check_bundle(bundle)

    assert result.passed is True
    assert result.failures == []


def test_bundle_with_nan_output_fails_sanity_check():
    bundle = {"pipeline": _IdentityPipeline(), "model": _NaNModel(), "threshold": 0.5}
    result = sanity_check_bundle(bundle)

    assert result.passed is False
    assert any("NaN" in f for f in result.failures)


def test_bundle_with_out_of_range_probability_fails_sanity_check():
    bundle = {"pipeline": _IdentityPipeline(), "model": _OutOfRangeModel(), "threshold": 0.5}
    result = sanity_check_bundle(bundle)

    assert result.passed is False
    assert any("rentang" in f for f in result.failures)


def test_bundle_that_crashes_on_predict_fails_sanity_check():
    bundle = {"pipeline": _CrashingPipeline(), "model": _NaNModel(), "threshold": 0.5}
    result = sanity_check_bundle(bundle)

    assert result.passed is False
    assert any("Exception" in f for f in result.failures)


def test_sample_inputs_used_are_deterministic_and_multi_row():
    from churn_prediction.inference.artifact_validation import _sample_inputs

    df = _sample_inputs()
    assert len(df) >= 3
    assert "tenure" in df.columns
