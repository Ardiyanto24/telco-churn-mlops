"""Constraint per kolom untuk skema data mentah (batch) dan request (real-time).

Sumber tunggal dipakai baik `raw_schema.py` (pandera) maupun `request_schema.py`
(Pydantic) -- lihat milestones/1.3-skema-validasi-input/decisions.md Keputusan #2.
Bukan keputusan desain baru: kategori/rentang diambil langsung dari
docs/03-notebook-audit/notebook-audit.md Bagian A (nilai unik EDA Insight 6) dan
Bagian H.3 (CHECK constraint tabel telco_customers_synthetic, Keputusan #1).

Column grouping (BINARY_COLS, ADDON_COLS, dst) di-reuse dari
churn_prediction.transform.constants -- bukan ditulis ulang.
"""

from churn_prediction.transform import constants as transform_constants

# -- Nilai kategori mentah (belum di-encode), lihat notebook-audit.md Bagian A --
_YES_NO = ["Yes", "No"]
_YES_NO_NO_INTERNET = ["Yes", "No", "No internet service"]
_YES_NO_NO_PHONE = ["Yes", "No", "No phone service"]

# Kolom kategorikal (teks/int diskret) -> daftar nilai valid.
# BINARY_COLS dan ADDON_COLS di-reuse dari transform.constants (Keputusan #2) --
# bukan ditulis ulang daftar nama kolomnya, hanya nilai valid yang ditambahkan di sini.
CATEGORICAL_COLUMNS: dict = {
    "gender": ["Female", "Male"],
    "senior_citizen": [0, 1],
    **{c: _YES_NO for c in transform_constants.BINARY_COLS},  # partner, dependents, phone_service, paperless_billing
    "multiple_lines": _YES_NO_NO_PHONE,
    "internet_service": ["DSL", "Fiber optic", "No"],
    **{c: _YES_NO_NO_INTERNET for c in transform_constants.ADDON_COLS},  # 6 kolom addon
    "contract": ["Month-to-month", "One year", "Two year"],
    "payment_method": [
        "Bank transfer (automatic)",
        "Credit card (automatic)",
        "Electronic check",
        "Mailed check",
    ],
}

# Kolom numerik kontinu -> rentang valid (notebook-audit.md Bagian H.3 CHECK constraint).
# tenure: BETWEEN 1 AND 72 (inklusif kedua sisi).
# monthly_charges: > 0 (CHECK monthly_charges > 0, eksklusif).
# total_charges: >= 0 (CHECK total_charges >= 0, inklusif).
NUMERIC_RANGES: dict = {
    "tenure": {"dtype": int, "ge": 1, "le": 72},
    "monthly_charges": {"dtype": float, "gt": 0},
    "total_charges": {"dtype": float, "ge": 0},
}

# 19 kolom fitur -- identik kontrak input churn_prediction.transform.PreprocessingPipeline
# (docs/03-notebook-audit/notebook-audit.md Bagian H.3 dikurangi target `churn`).
FEATURE_COLUMNS = list(CATEGORICAL_COLUMNS.keys()) + list(NUMERIC_RANGES.keys())
