"""Konstanta monitoring drift -- Milestone 3.6.

Klasifikasi tipe 29 fitur final model DIAMBIL LANGSUNG dari
``docs/03-notebook-audit/notebook-audit.md`` Bagian C.1-C.5 (sumber
kebenaran audit notebook DS), bukan diklasifikasi ulang di sini. Nama kolom
dikonfirmasi persis lewat pemanggilan nyata
``registry.load_active_pipeline().transform(df)`` terhadap 1 baris sampel
(lihat milestones/3.6-monitoring-drift-kualitas-model/logs.md).

- C.1 (4 fitur, numerik kontinu di-scale StandardScaler) -> "numeric" -> Tier 2 KS-test.
- C.2 (7 fitur, binary 0/1) + C.3 (1 fitur, integer diskret) + C.4 (7 fitur,
  structural -1/0/1) + C.5 (10 fitur, one-hot 0/1) -> "categorical" -> Tier 2 Chi-square.

Total: 4 + 25 = 29, cocok ``X_train_proc.shape[1]==29`` (notebook-audit.md
Bagian C).
"""

FEATURE_TYPES: dict[str, str] = {
    # C.1 -- numerik kontinu
    "tenure": "numeric",
    "monthly_charges": "numeric",
    "tc_residual": "numeric",
    "monthly_to_total_ratio": "numeric",
    # C.2 -- binary 0/1
    "senior_citizen": "categorical",
    "partner": "categorical",
    "dependents": "categorical",
    "phone_service": "categorical",
    "paperless_billing": "categorical",
    "is_auto_payment": "categorical",
    "has_any_addon": "categorical",
    # C.3 -- integer diskret
    "service_count": "categorical",
    # C.4 -- structural -1/0/1
    "online_security": "categorical",
    "online_backup": "categorical",
    "device_protection": "categorical",
    "tech_support": "categorical",
    "streaming_tv": "categorical",
    "streaming_movies": "categorical",
    "multiple_lines": "categorical",
    # C.5 -- one-hot 0/1
    "contract_One year": "categorical",
    "contract_Two year": "categorical",
    "internet_service_Fiber optic": "categorical",
    "internet_service_No": "categorical",
    "payment_method_Credit card (automatic)": "categorical",
    "payment_method_Electronic check": "categorical",
    "payment_method_Mailed check": "categorical",
    "tenure_group_G2_2_18": "categorical",
    "tenure_group_G3_18_44": "categorical",
    "tenure_group_G4_44_72": "categorical",
}

# Output prediksi -- kontinu (probabilitas [0,1]), diperlakukan sama seperti
# fitur numerik (Tier 2 KS-test), tapi dipisah dari FEATURE_TYPES karena
# bukan fitur INPUT model.
PREDICTION_OUTPUT_NAME = "churn_probability"
PREDICTION_OUTPUT_TYPE = "numeric"

assert len(FEATURE_TYPES) == 29
assert sum(1 for t in FEATURE_TYPES.values() if t == "numeric") == 4
assert sum(1 for t in FEATURE_TYPES.values() if t == "categorical") == 25

# ── Threshold PSI (Population Stability Index) -- konvensi industri lama
# dipakai luas (credit scoring/MLOps), BUKAN angka yang dikarang untuk
# proyek ini. Lihat milestones/3.6-.../decisions.md Keputusan #7.
PSI_FLAG_THRESHOLD = 0.1
PSI_STOP_THRESHOLD = 0.25

# ── Threshold p-value -- konvensi signifikansi statistik standar (alpha).
PVALUE_FLAG_THRESHOLD = 0.05
PVALUE_STOP_THRESHOLD = 0.01

VERDICT_ORDER = {"pass": 0, "flag": 1, "stop": 2}

# ── Baseline sample size -- cukup besar untuk KS-test/Chi-square bermakna
# tanpa overhead menyimpan seluruh 594.194 baris telco_customers_source.
BASELINE_SAMPLE_SIZE = 10_000

# ── Jumlah bin PSI default (desil) untuk fitur numerik. Fitur kategorikal
# pakai nilai unik sebagai bin (tidak butuh n_bins).
PSI_NUMERIC_BINS = 10
