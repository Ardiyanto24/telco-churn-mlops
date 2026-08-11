"""Skema/validasi request real-time API -- Pydantic.

Dibangun terprogram dari `schema/constants.py` (Keputusan #2, satu sumber
constraint dipakai raw_schema dan request_schema) -- bukan menuliskan ulang
daftar kategori/rentang secara manual di sini.

Kontrak: 19 field snake_case, IDENTIK nama kolom data mentah (Keputusan #4,
milestones/1.3-skema-validasi-input/decisions.md) -- pemetaan field-ke-kolom
adalah identity mapping, didokumentasikan penuh di `schema/__init__.py`.
Tidak ada field ID/correlation -- itu wewenang desain API Milestone 3.2.
"""

from typing import Literal

from pydantic import Field, create_model

from . import constants

_field_definitions: dict = {}

for _col, _categories in constants.CATEGORICAL_COLUMNS.items():
    _literal_type = Literal[tuple(_categories)]
    _field_definitions[_col] = (_literal_type, ...)

for _col, _spec in constants.NUMERIC_RANGES.items():
    _field_kwargs = {}
    if "ge" in _spec:
        _field_kwargs["ge"] = _spec["ge"]
    if "le" in _spec:
        _field_kwargs["le"] = _spec["le"]
    if "gt" in _spec:
        _field_kwargs["gt"] = _spec["gt"]
    _field_definitions[_col] = (_spec["dtype"], Field(..., **_field_kwargs))

ChurnPredictionRequest = create_model("ChurnPredictionRequest", **_field_definitions)
"""Pydantic BaseModel untuk request real-time API, 19 field snake_case.

Penggunaan:
    from churn_prediction.schema.request_schema import ChurnPredictionRequest
    request = ChurnPredictionRequest(**payload)  # raise pydantic.ValidationError kalau invalid
"""
