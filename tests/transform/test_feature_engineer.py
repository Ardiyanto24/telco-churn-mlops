import pandas as pd
import pytest

from churn_prediction.transform.feature_engineer import FeatureEngineer


def _base_row(**overrides):
    row = {
        "tenure": 29,
        "monthly_charges": 60.10,
        "total_charges": 1653.85,
        "payment_method": "Mailed check",
        "online_security": "Yes",
        "online_backup": "No",
        "device_protection": "Yes",
        "tech_support": "Yes",
        "streaming_tv": "No",
        "streaming_movies": "No",
    }
    row.update(overrides)
    return row


def test_tc_residual_and_ratio_real_row_id0():
    # Baris nyata id=0 (notebook-audit.md Bagian H.2, dikonfirmasi via Supabase).
    df = pd.DataFrame([_base_row()])
    out = FeatureEngineer().fit_transform(df)

    expected_residual = 1653.85 - (29 * 60.10)
    assert out["tc_residual"].iloc[0] == pytest.approx(expected_residual)

    expected_ratio = 60.10 / 1653.85
    assert out["monthly_to_total_ratio"].iloc[0] == pytest.approx(expected_ratio)

    # PaymentMethod 'Mailed check' bukan metode otomatis
    assert out["is_auto_payment"].iloc[0] == 0


def test_monthly_to_total_ratio_fallback_when_total_charges_zero():
    df = pd.DataFrame([_base_row(total_charges=0.0)])
    out = FeatureEngineer().fit_transform(df)
    assert out["monthly_to_total_ratio"].iloc[0] == 1.0


@pytest.mark.parametrize(
    "tenure,expected_group",
    [
        (0, "G1_0_2"),
        (1, "G1_0_2"),
        (2, "G1_0_2"),
        (17, "G2_2_18"),
        (18, "G2_2_18"),
        (43, "G3_18_44"),
        (44, "G3_18_44"),
        (71, "G4_44_72"),
        (72, "G4_44_72"),
    ],
)
def test_tenure_group_bin_boundaries(tenure, expected_group):
    df = pd.DataFrame([_base_row(tenure=tenure)])
    out = FeatureEngineer().fit_transform(df)
    assert out["tenure_group"].iloc[0] == expected_group


def test_is_auto_payment_true_for_automatic_methods():
    for method in ["Bank transfer (automatic)", "Credit card (automatic)"]:
        df = pd.DataFrame([_base_row(payment_method=method)])
        out = FeatureEngineer().fit_transform(df)
        assert out["is_auto_payment"].iloc[0] == 1


def test_service_count_and_has_any_addon_all_no_internet_service():
    row = _base_row(
        online_security="No internet service",
        online_backup="No internet service",
        device_protection="No internet service",
        tech_support="No internet service",
        streaming_tv="No internet service",
        streaming_movies="No internet service",
    )
    df = pd.DataFrame([row])
    out = FeatureEngineer().fit_transform(df)
    assert out["service_count"].iloc[0] == 0
    assert out["has_any_addon"].iloc[0] == 0


def test_service_count_counts_only_yes():
    row = _base_row(
        online_security="Yes",
        online_backup="Yes",
        device_protection="No",
        tech_support="No internet service",
        streaming_tv="Yes",
        streaming_movies="No",
    )
    df = pd.DataFrame([row])
    out = FeatureEngineer().fit_transform(df)
    assert out["service_count"].iloc[0] == 3
    assert out["has_any_addon"].iloc[0] == 1
