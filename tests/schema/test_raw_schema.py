import pandas as pd
import pandera.errors
import pytest

from churn_prediction.schema.raw_schema import RawDataSchema


def _valid_row(**overrides):
    row = {
        "gender": "Male",
        "senior_citizen": 0,
        "partner": "Yes",
        "dependents": "No",
        "tenure": 29,
        "phone_service": "Yes",
        "multiple_lines": "No",
        "internet_service": "DSL",
        "online_security": "Yes",
        "online_backup": "No",
        "device_protection": "Yes",
        "tech_support": "Yes",
        "streaming_tv": "No",
        "streaming_movies": "No",
        "contract": "One year",
        "paperless_billing": "Yes",
        "payment_method": "Mailed check",
        "monthly_charges": 60.10,
        "total_charges": 1653.85,
    }
    row.update(overrides)
    return row


def test_valid_row_passes():
    df = pd.DataFrame([_valid_row()])
    validated = RawDataSchema.validate(df)
    assert len(validated) == 1


def test_missing_column_rejected():
    df = pd.DataFrame([_valid_row()]).drop(columns=["tenure"])
    with pytest.raises(pandera.errors.SchemaError, match="tenure"):
        RawDataSchema.validate(df)


def test_wrong_type_rejected():
    df = pd.DataFrame([_valid_row(tenure="abc")])
    with pytest.raises(pandera.errors.SchemaError):
        RawDataSchema.validate(df)


def test_tenure_above_max_rejected():
    df = pd.DataFrame([_valid_row(tenure=200)])
    with pytest.raises(pandera.errors.SchemaError, match="tenure"):
        RawDataSchema.validate(df)


def test_tenure_zero_rejected():
    df = pd.DataFrame([_valid_row(tenure=0)])
    with pytest.raises(pandera.errors.SchemaError, match="tenure"):
        RawDataSchema.validate(df)


def test_negative_monthly_charges_rejected():
    df = pd.DataFrame([_valid_row(monthly_charges=-5.0)])
    with pytest.raises(pandera.errors.SchemaError, match="monthly_charges"):
        RawDataSchema.validate(df)


def test_invalid_senior_citizen_value_rejected():
    df = pd.DataFrame([_valid_row(senior_citizen=2)])
    with pytest.raises(pandera.errors.SchemaError, match="senior_citizen"):
        RawDataSchema.validate(df)


def test_unknown_category_rejected():
    df = pd.DataFrame([_valid_row(contract="Weekly")])
    with pytest.raises(pandera.errors.SchemaError, match="contract"):
        RawDataSchema.validate(df)
