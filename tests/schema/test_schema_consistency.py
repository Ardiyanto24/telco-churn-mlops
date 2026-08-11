"""KK2: skema request real-time API dan skema data mentah, dibandingkan
berdampingan, harus menunjukkan pemetaan yang konsisten -- tidak ada
field/kolom bermakna sama tapi didefinisikan beda.

Pendekatan "behavioral": bukan introspeksi struktur internal pandera/pydantic
(rapuh, terikat versi library), tapi menguji APAKAH KEDUA skema
menerima/menolak nilai yang sama secara identik -- ini yang benar-benar
dimaksud "pemetaan konsisten".
"""

import pandas as pd
import pandera.errors
import pydantic
import pytest

from churn_prediction.schema import constants
from churn_prediction.schema.raw_schema import RawDataSchema
from churn_prediction.schema.request_schema import ChurnPredictionRequest

VALID_ROW = {
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


def _raw_accepts(row: dict) -> bool:
    try:
        RawDataSchema.validate(pd.DataFrame([row]))
        return True
    except pandera.errors.SchemaError:
        return False


def _request_accepts(row: dict) -> bool:
    try:
        ChurnPredictionRequest(**row)
        return True
    except pydantic.ValidationError:
        return False


def test_field_sets_identical():
    raw_cols = set(RawDataSchema.columns.keys())
    request_fields = set(ChurnPredictionRequest.model_fields.keys())
    constants_cols = set(constants.FEATURE_COLUMNS)
    assert raw_cols == request_fields == constants_cols


def test_valid_row_accepted_by_both():
    assert _raw_accepts(VALID_ROW)
    assert _request_accepts(VALID_ROW)


@pytest.mark.parametrize("col", list(constants.CATEGORICAL_COLUMNS.keys()))
def test_categorical_columns_accept_same_valid_values(col):
    for valid_value in constants.CATEGORICAL_COLUMNS[col]:
        row = {**VALID_ROW, col: valid_value}
        assert _raw_accepts(row) == _request_accepts(row) == True, (col, valid_value)


@pytest.mark.parametrize("col", list(constants.CATEGORICAL_COLUMNS.keys()))
def test_categorical_columns_reject_same_invalid_value(col):
    row = {**VALID_ROW, col: "__NILAI_TAK_DIKENAL__"}
    assert _raw_accepts(row) == _request_accepts(row) == False, col


@pytest.mark.parametrize("col,spec", list(constants.NUMERIC_RANGES.items()))
def test_numeric_columns_reject_same_out_of_range_values(col, spec):
    # nilai di bawah batas bawah (kalau ada ge/gt)
    if "ge" in spec:
        row = {**VALID_ROW, col: spec["ge"] - 1}
        assert _raw_accepts(row) == _request_accepts(row) == False, (col, "below ge")
    if "gt" in spec:
        row = {**VALID_ROW, col: spec["gt"]}  # persis di batas, gt eksklusif -> harus ditolak
        assert _raw_accepts(row) == _request_accepts(row) == False, (col, "at gt boundary")
    # nilai di atas batas atas (kalau ada le)
    if "le" in spec:
        row = {**VALID_ROW, col: spec["le"] + 1}
        assert _raw_accepts(row) == _request_accepts(row) == False, (col, "above le")


@pytest.mark.parametrize("col,spec", list(constants.NUMERIC_RANGES.items()))
def test_numeric_columns_accept_same_boundary_valid_values(col, spec):
    if "ge" in spec:
        row = {**VALID_ROW, col: spec["ge"]}
        assert _raw_accepts(row) == _request_accepts(row) == True, (col, "at ge boundary")
    if "le" in spec:
        row = {**VALID_ROW, col: spec["le"]}
        assert _raw_accepts(row) == _request_accepts(row) == True, (col, "at le boundary")
