import pydantic
import pytest

from churn_prediction.schema.request_schema import ChurnPredictionRequest


def _valid_payload(**overrides):
    payload = {
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
    payload.update(overrides)
    return payload


def test_valid_payload_passes():
    req = ChurnPredictionRequest(**_valid_payload())
    assert req.tenure == 29


def test_missing_field_rejected():
    payload = _valid_payload()
    del payload["tenure"]
    with pytest.raises(pydantic.ValidationError, match="tenure"):
        ChurnPredictionRequest(**payload)


def test_wrong_type_rejected():
    with pytest.raises(pydantic.ValidationError, match="tenure"):
        ChurnPredictionRequest(**_valid_payload(tenure="abc"))


def test_tenure_above_max_rejected():
    with pytest.raises(pydantic.ValidationError, match="tenure"):
        ChurnPredictionRequest(**_valid_payload(tenure=200))


def test_tenure_zero_rejected():
    with pytest.raises(pydantic.ValidationError, match="tenure"):
        ChurnPredictionRequest(**_valid_payload(tenure=0))


def test_negative_monthly_charges_rejected():
    with pytest.raises(pydantic.ValidationError, match="monthly_charges"):
        ChurnPredictionRequest(**_valid_payload(monthly_charges=-5.0))


def test_invalid_senior_citizen_value_rejected():
    with pytest.raises(pydantic.ValidationError, match="senior_citizen"):
        ChurnPredictionRequest(**_valid_payload(senior_citizen=2))


def test_unknown_category_rejected():
    with pytest.raises(pydantic.ValidationError, match="contract"):
        ChurnPredictionRequest(**_valid_payload(contract="Weekly"))
