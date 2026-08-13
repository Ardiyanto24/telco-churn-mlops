"""Sanity check artifact -- gerbang sebelum registrasi, Milestone 2.8.

``sanity_check_bundle()`` menjalankan bundle (belum teregistrasi) lewat jalur
kode PRODUKSI yang sama persis (``ChurnPyfuncModel.predict()``, bukan
implementasi ulang transform+predict_proba+threshold) terhadap input uji
sintetis -- membuktikan artifact bisa dimuat dan menghasilkan output
berbentuk/bertipe sesuai kontrak sebelum layak jadi kandidat versi
terregistrasi (Bagian 5.5 dokumen arsitektur). Bukan evaluasi performa model
(itu keputusan Data Scientist, di luar cakupan) -- murni gerbang teknis.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .pyfunc_model import ChurnPyfuncModel

_EXPECTED_COLUMNS = {"churn_probability", "churn_label"}


@dataclass
class SanityCheckResult:
    passed: bool
    failures: list = field(default_factory=list)


def _sample_inputs() -> pd.DataFrame:
    """Input uji sintetis (skema sama ``RawDataSchema``, pola sama
    ``_valid_row()`` di ``tests/inference/test_predictor.py``) -- beberapa
    baris valid dengan variasi nilai numerik, bukan cuma satu baris."""
    base = {
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
    variations = [
        {},
        {"tenure": 1, "monthly_charges": 20.0, "total_charges": 20.0},
        {"tenure": 72, "monthly_charges": 118.75, "total_charges": 8564.75, "contract": "Two year"},
    ]
    rows = []
    for v in variations:
        row = dict(base)
        row.update(v)
        rows.append(row)
    return pd.DataFrame(rows)


def sanity_check_bundle(bundle: dict) -> SanityCheckResult:
    """Jalankan ``bundle`` (``{"pipeline", "model", "threshold"}``, hasil
    ``build_bundle()``) lewat ``ChurnPyfuncModel.predict()`` terhadap input
    uji sintetis. ``context`` pyfunc tidak dipakai di dalam ``predict()``
    (cuma ``load_context()`` yang mengaksesnya) -- aman diisi ``None``,
    menghindari perlu MLflow artifact context sungguhan untuk bundle yang
    belum diregistrasi."""
    model = ChurnPyfuncModel()
    model._pipeline = bundle["pipeline"]
    model._model = bundle["model"]
    model._threshold = bundle["threshold"]

    df = _sample_inputs()
    try:
        result = model.predict(None, df)
    except Exception as exc:
        return SanityCheckResult(passed=False, failures=[f"Exception saat predict(): {exc!r}"])

    failures = []
    if set(result.columns) != _EXPECTED_COLUMNS:
        failures.append(f"Kolom output tidak sesuai kontrak: {list(result.columns)} (harap {_EXPECTED_COLUMNS})")
        return SanityCheckResult(passed=False, failures=failures)

    if len(result) != len(df):
        failures.append(f"Jumlah baris output ({len(result)}) != input ({len(df)})")

    proba = result["churn_probability"]
    if proba.isna().any():
        failures.append("churn_probability mengandung NaN")
    elif np.isinf(proba.to_numpy(dtype=float)).any():
        failures.append("churn_probability mengandung inf")
    elif not proba.between(0, 1).all():
        failures.append(f"churn_probability di luar rentang [0,1]: {proba.tolist()}")

    labels = result["churn_label"]
    if not set(labels.unique()).issubset({0, 1}):
        failures.append(f"churn_label bukan {{0,1}}: {labels.unique().tolist()}")

    return SanityCheckResult(passed=not failures, failures=failures)
