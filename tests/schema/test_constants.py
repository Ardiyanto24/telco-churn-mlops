"""Verifikasi manual: tiap constraint di schema/constants.py dicocokkan satu-satu
terhadap docs/03-notebook-audit/notebook-audit.md Bagian A (nilai unik EDA) dan
Bagian H.3 (CHECK constraint telco_customers_synthetic)."""

from churn_prediction.schema import constants


def test_total_19_feature_columns():
    assert len(constants.FEATURE_COLUMNS) == 19
    assert len(set(constants.FEATURE_COLUMNS)) == 19  # tidak ada duplikat


# -- Bagian A notebook-audit.md: nilai unik per kolom kategorikal --

def test_gender_categories():
    assert set(constants.CATEGORICAL_COLUMNS["gender"]) == {"Female", "Male"}


def test_senior_citizen_categories():
    assert set(constants.CATEGORICAL_COLUMNS["senior_citizen"]) == {0, 1}


def test_binary_yes_no_columns():
    for col in ["partner", "dependents", "phone_service", "paperless_billing"]:
        assert set(constants.CATEGORICAL_COLUMNS[col]) == {"Yes", "No"}, col


def test_multiple_lines_categories():
    assert set(constants.CATEGORICAL_COLUMNS["multiple_lines"]) == {"Yes", "No", "No phone service"}


def test_internet_service_categories():
    assert set(constants.CATEGORICAL_COLUMNS["internet_service"]) == {"DSL", "Fiber optic", "No"}


def test_addon_columns_categories():
    addon_cols = ["online_security", "online_backup", "device_protection", "tech_support", "streaming_tv", "streaming_movies"]
    for col in addon_cols:
        assert set(constants.CATEGORICAL_COLUMNS[col]) == {"Yes", "No", "No internet service"}, col


def test_contract_categories():
    assert set(constants.CATEGORICAL_COLUMNS["contract"]) == {"Month-to-month", "One year", "Two year"}


def test_payment_method_categories():
    assert set(constants.CATEGORICAL_COLUMNS["payment_method"]) == {
        "Bank transfer (automatic)",
        "Credit card (automatic)",
        "Electronic check",
        "Mailed check",
    }


# -- Bagian H.3 notebook-audit.md: CHECK constraint telco_customers_synthetic --

def test_tenure_range_matches_check_constraint():
    spec = constants.NUMERIC_RANGES["tenure"]
    assert spec["ge"] == 1 and spec["le"] == 72  # CHECK (tenure BETWEEN 1 AND 72)


def test_monthly_charges_range_matches_check_constraint():
    spec = constants.NUMERIC_RANGES["monthly_charges"]
    assert spec["gt"] == 0  # CHECK (monthly_charges > 0)


def test_total_charges_range_matches_check_constraint():
    spec = constants.NUMERIC_RANGES["total_charges"]
    assert spec["ge"] == 0  # CHECK (total_charges >= 0)


def test_column_groupings_reused_from_transform_constants():
    """Keputusan #2: pastikan tidak ada penulisan ulang independen -- BINARY_COLS/
    ADDON_COLS di schema harus persis sama dengan transform.constants."""
    from churn_prediction.transform import constants as transform_constants

    for col in transform_constants.BINARY_COLS:
        assert col in constants.CATEGORICAL_COLUMNS
    for col in transform_constants.ADDON_COLS:
        assert col in constants.CATEGORICAL_COLUMNS
