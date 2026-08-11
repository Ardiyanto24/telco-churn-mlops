import pandas as pd

from churn_prediction.transform.pipeline import PreprocessingPipeline

EXPECTED_29_COLUMNS = {
    # C.1 numerik kontinu
    "tenure",
    "monthly_charges",
    "tc_residual",
    "monthly_to_total_ratio",
    # C.2 binary
    "senior_citizen",
    "partner",
    "dependents",
    "phone_service",
    "paperless_billing",
    "is_auto_payment",
    "has_any_addon",
    # C.3 integer diskret
    "service_count",
    # C.4 structural
    "online_security",
    "online_backup",
    "device_protection",
    "tech_support",
    "streaming_tv",
    "streaming_movies",
    "multiple_lines",
    # C.5 one-hot (drop_first, mencakup semua kategori -> dummy penuh)
    "contract_One year",
    "contract_Two year",
    "internet_service_Fiber optic",
    "internet_service_No",
    "payment_method_Credit card (automatic)",
    "payment_method_Electronic check",
    "payment_method_Mailed check",
    "tenure_group_G2_2_18",
    "tenure_group_G3_18_44",
    "tenure_group_G4_44_72",
}


def _sample_raw_df():
    """DataFrame buatan tangan, 19 kolom fitur snake_case (skema H.3 minus churn),
    mencakup seluruh kategori Contract/InternetService/PaymentMethod/tenure_group
    supaya OHE menghasilkan dummy set penuh."""
    rows = [
        # tenure_group G1 (0-2), Contract Month-to-month (baseline), InternetService DSL (baseline), PaymentMethod Bank transfer (baseline)
        dict(
            gender="Male", senior_citizen=0, partner="Yes", dependents="No",
            tenure=1, phone_service="Yes", multiple_lines="No",
            internet_service="DSL", online_security="Yes", online_backup="No",
            device_protection="Yes", tech_support="No", streaming_tv="No", streaming_movies="No",
            contract="Month-to-month", paperless_billing="Yes",
            payment_method="Bank transfer (automatic)", monthly_charges=50.0, total_charges=50.0,
        ),
        # tenure_group G2 (2-18), Contract One year, InternetService Fiber optic, PaymentMethod Credit card
        dict(
            gender="Female", senior_citizen=1, partner="No", dependents="Yes",
            tenure=10, phone_service="No", multiple_lines="No phone service",
            internet_service="Fiber optic", online_security="No", online_backup="Yes",
            device_protection="No", tech_support="Yes", streaming_tv="Yes", streaming_movies="No",
            contract="One year", paperless_billing="No",
            payment_method="Credit card (automatic)", monthly_charges=80.0, total_charges=800.0,
        ),
        # tenure_group G3 (18-44), Contract Two year, InternetService No, PaymentMethod Electronic check
        dict(
            gender="Male", senior_citizen=0, partner="Yes", dependents="Yes",
            tenure=30, phone_service="Yes", multiple_lines="Yes",
            internet_service="No", online_security="No internet service", online_backup="No internet service",
            device_protection="No internet service", tech_support="No internet service",
            streaming_tv="No internet service", streaming_movies="No internet service",
            contract="Two year", paperless_billing="Yes",
            payment_method="Electronic check", monthly_charges=20.0, total_charges=600.0,
        ),
        # tenure_group G4 (44-72), PaymentMethod Mailed check
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


def test_fit_transform_produces_29_columns_matching_audit():
    df = _sample_raw_df()
    pipeline = PreprocessingPipeline()
    out = pipeline.fit_transform(df)

    assert out.shape == (4, 29)
    assert set(out.columns) == EXPECTED_29_COLUMNS
    assert not out.isnull().any().any()


def test_transform_after_fit_on_new_data():
    df = _sample_raw_df()
    pipeline = PreprocessingPipeline()
    pipeline.fit(df)

    new_row = _sample_raw_df().iloc[[0]]
    out = pipeline.transform(new_row)
    assert out.shape == (1, 29)
    assert set(out.columns) == EXPECTED_29_COLUMNS


def test_kk1_repeated_transform_calls_are_identical():
    """KK1: dipanggil berulang dengan input sama -> output identik."""
    df = _sample_raw_df()
    pipeline = PreprocessingPipeline()
    pipeline.fit(df)

    new_row = _sample_raw_df().iloc[[1]]
    out_first = pipeline.transform(new_row)
    out_second = pipeline.transform(new_row)
    out_third = pipeline.transform(new_row)

    pd.testing.assert_frame_equal(out_first, out_second)
    pd.testing.assert_frame_equal(out_first, out_third)


def test_kk1_fit_does_not_accumulate_state_across_calls():
    """KK1: fit_transform pada dua DataFrame independen berurutan -- parameter
    fit kedua tidak 'mengingat' data pertama (ter-overwrite bersih)."""
    pipeline = PreprocessingPipeline()

    df_a = _sample_raw_df().iloc[[0, 1]]  # hanya tenure_group G1, G2
    pipeline.fit_transform(df_a)
    scaler_mean_after_a = pipeline.scaler_wrapper_._scaler.mean_.copy()

    df_b = _sample_raw_df().iloc[[2, 3]]  # hanya tenure_group G3, G4 -- data BEDA total
    pipeline.fit_transform(df_b)
    scaler_mean_after_b = pipeline.scaler_wrapper_._scaler.mean_
    ohe_categories_after_b = pipeline.ohe_wrapper_._encoder.categories_

    # parameter fit kedua harus BEDA dari yang pertama (bukti tidak ada state
    # tersembunyi yang menggabungkan/mengingat fit sebelumnya)
    assert not (scaler_mean_after_a == scaler_mean_after_b).all()
    # kategori fit kedua hanya berasal dari df_b, bukan gabungan df_a+df_b
    contract_categories_b = ohe_categories_after_b[0]
    assert "Month-to-month" not in contract_categories_b  # hanya ada di df_a
