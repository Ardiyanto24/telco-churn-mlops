"""Unit test logika ``scripts.verify_before_promotion.verify_before_promotion()``
-- Milestone 2.8 Checkpoint 2.

Mock ``load_active_model``/``load_model_by_version`` -- murni menguji logika
ambang/verdict, TIDAK butuh registry/DB sungguhan (beda dari
Task 8 yang menjalankan skrip terhadap infrastruktur real).
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from scripts.verify_before_promotion import CHURN_RATE_DELTA_THRESHOLD_PP, verify_before_promotion


class _FakeModel:
    def __init__(self, churn_probability, raises=None):
        self._proba = churn_probability
        self._raises = raises

    def predict(self, df):
        if self._raises:
            raise self._raises
        n = len(df)
        proba = np.array(self._proba[:n]) if len(self._proba) >= n else np.resize(self._proba, n)
        return pd.DataFrame({
            "churn_probability": proba,
            "churn_label": (proba >= 0.5).astype(int),
        })


def _df(n=10):
    return pd.DataFrame({"tenure": range(1, n + 1)})


def test_candidate_exception_fails_mandatory_check():
    champion = _FakeModel([0.3] * 10)
    candidate = _FakeModel([0.3] * 10, raises=RuntimeError("boom"))

    with patch("scripts.verify_before_promotion.load_active_model", return_value=champion), \
         patch("scripts.verify_before_promotion.load_model_by_version", return_value=candidate):
        result = verify_before_promotion(_df(), "2")

    assert result["mandatory_passed"] is False
    assert "Exception" in result["error"]


def test_candidate_nan_fails_mandatory_check():
    champion = _FakeModel([0.3] * 10)
    candidate = _FakeModel([np.nan] * 10)

    with patch("scripts.verify_before_promotion.load_active_model", return_value=champion), \
         patch("scripts.verify_before_promotion.load_model_by_version", return_value=candidate):
        result = verify_before_promotion(_df(), "2")

    assert result["mandatory_passed"] is False
    assert "NaN" in result["error"]


def test_close_churn_rate_verdict_pass():
    # champion: 3/10 label=1 (30%), candidate: 4/10 label=1 (40%) -- delta 10pp < 20pp
    champion = _FakeModel([0.6, 0.6, 0.6, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
    candidate = _FakeModel([0.6, 0.6, 0.6, 0.6, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])

    with patch("scripts.verify_before_promotion.load_active_model", return_value=champion), \
         patch("scripts.verify_before_promotion.load_model_by_version", return_value=candidate):
        result = verify_before_promotion(_df(), "2")

    assert result["mandatory_passed"] is True
    assert result["verdict"] == "pass"
    assert result["delta_pp"] == pytest.approx(10.0)


def test_far_churn_rate_verdict_flag():
    # champion: 1/10 label=1 (10%), candidate: 9/10 label=1 (90%) -- delta 80pp >= 20pp
    champion = _FakeModel([0.6] + [0.1] * 9)
    candidate = _FakeModel([0.6] * 9 + [0.1])

    with patch("scripts.verify_before_promotion.load_active_model", return_value=champion), \
         patch("scripts.verify_before_promotion.load_model_by_version", return_value=candidate):
        result = verify_before_promotion(_df(), "2")

    assert result["mandatory_passed"] is True
    assert result["verdict"] == "flag"
    assert result["delta_pp"] >= CHURN_RATE_DELTA_THRESHOLD_PP
