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


def test_get_feature_names_out_is_identity_passthrough():
    # M1.4 Task 2 (audit Checkpoint 1, Temuan 1): 0% coverage sebelumnya.
    scaler = ScalerWrapper()
    names = ["tenure", "monthly_charges"]
    assert scaler.get_feature_names_out(names) == names


def test_no_target_columns_present_is_noop():
    # M1.4 Task 4 (audit Checkpoint 1, Temuan 3): skenario "tidak ada kolom
    # target sama sekali di input" -- cols_present_ kosong -- belum pernah diuji
    # (37->39, 43->45 di scaler_wrapper.py).
    df = pd.DataFrame({"is_auto_payment": [1, 0, 1], "service_count": [2, 0, 5]})
    scaler = ScalerWrapper()
    out = scaler.fit_transform(df)
    assert scaler.cols_present_ == []
    pd.testing.assert_frame_equal(out, df)  # tidak ada perubahan sama sekali

    # transform() terpisah pada data lain juga harus no-op yang sama
    out2 = scaler.transform(df)
    pd.testing.assert_frame_equal(out2, df)
