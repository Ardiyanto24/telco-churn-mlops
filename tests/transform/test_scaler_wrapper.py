import pandas as pd
import pytest

from churn_prediction.transform.scaler_wrapper import ScalerWrapper


def test_scaled_columns_mean_zero_std_one():
    df = pd.DataFrame(
        {
            "tenure": [1.0, 2.0, 3.0, 4.0, 5.0],
            "monthly_charges": [10.0, 20.0, 30.0, 40.0, 50.0],
            "tc_residual": [-5.0, 0.0, 5.0, 10.0, 15.0],
            "monthly_to_total_ratio": [0.1, 0.2, 0.3, 0.4, 0.5],
        }
    )
    scaler = ScalerWrapper()
    out = scaler.fit_transform(df)

    for c in ["tenure", "monthly_charges", "tc_residual", "monthly_to_total_ratio"]:
        assert out[c].mean() == pytest.approx(0.0, abs=1e-8)
        assert out[c].std(ddof=0) == pytest.approx(1.0, rel=1e-6)


def test_non_target_columns_untouched():
    df = pd.DataFrame(
        {
            "tenure": [1.0, 2.0, 3.0],
            "monthly_charges": [10.0, 20.0, 30.0],
            "tc_residual": [1.0, 2.0, 3.0],
            "monthly_to_total_ratio": [0.1, 0.2, 0.3],
            "is_auto_payment": [1, 0, 1],
        }
    )
    scaler = ScalerWrapper()
    out = scaler.fit_transform(df)
    assert out["is_auto_payment"].tolist() == [1, 0, 1]
