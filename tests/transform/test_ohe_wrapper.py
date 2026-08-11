import pandas as pd

from churn_prediction.transform.ohe_wrapper import OHEWrapper


def _fit_sample():
    df = pd.DataFrame(
        {
            "contract": ["Month-to-month", "One year", "Two year"],
            "internet_service": ["DSL", "Fiber optic", "No"],
            "payment_method": [
                "Bank transfer (automatic)",
                "Credit card (automatic)",
                "Electronic check",
            ],
            "tenure_group": ["G1_0_2", "G2_2_18", "G3_18_44"],
        }
    )
    enc = OHEWrapper()
    enc.fit(df)
    return enc, df


def test_dummy_column_names_and_count_match_audit():
    enc, df = _fit_sample()
    out = enc.transform(df)

    # get_feature_names_out() sklearn pakai prefix nama kolom KITA (snake_case),
    # bukan PascalCase notebook -- yang penting jumlah & suffix kategori cocok
    # dengan docs/03-notebook-audit/notebook-audit.md Bagian C.5 (drop_first
    # membuang kategori pertama secara alfabetis).
    expected_cols = {
        "contract_One year",
        "contract_Two year",
        "internet_service_Fiber optic",
        "internet_service_No",
        "payment_method_Credit card (automatic)",
        "payment_method_Electronic check",
        "tenure_group_G2_2_18",
        "tenure_group_G3_18_44",
    }
    assert set(enc.ohe_feature_names_) == expected_cols
    assert set(out.columns) == expected_cols
    for c in ["contract", "internet_service", "payment_method", "tenure_group"]:
        assert c not in out.columns
    assert not out.isnull().any().any()


def test_unknown_category_does_not_raise():
    enc, df = _fit_sample()
    new_df = pd.DataFrame(
        {
            "contract": ["Month-to-month"],
            "internet_service": ["DSL"],
            "payment_method": ["Mailed check"],  # tidak ada di data fit
            "tenure_group": ["G4_44_72"],  # tidak ada di data fit
        }
    )
    # tidak boleh melempar exception (handle_unknown='ignore')
    out = enc.transform(new_df)
    assert out.shape[0] == 1


def test_fit_hanya_dipanggil_sekali_lalu_transform_data_lain():
    enc, df = _fit_sample()
    other = pd.DataFrame(
        {
            "contract": ["Two year"],
            "internet_service": ["No"],
            "payment_method": ["Bank transfer (automatic)"],
            "tenure_group": ["G1_0_2"],
        }
    )
    out = enc.transform(other)
    assert out.shape[0] == 1
    assert not out.isnull().any().any()
