"""Konstanta transformasi, di-port dari ``tccp-preprocessing-v2.ipynb`` cell 5.

Nama kolom di sini snake_case (skema ``telco_customers_synthetic``), berbeda dari
notebook asli yang PascalCase (skema ``telco_customers_source``) -- lihat
``milestones/1.2-modularisasi-preprocessing/decisions.md`` Keputusan #1.

PENTING: urutan elemen di tiap list konstanta HARUS persis sama posisinya dengan
notebook asli (Keputusan #4) -- ``StandardScaler``/``OneHotEncoder`` menyimpan
parameter fitted berbasis urutan posisi kolom saat fit, bukan nama kolom.
"""

TARGET = "churn"
CHURN_YES = "Yes"
CHURN_NO = "No"

# Kolom yang di-drop setelah feature engineering (lihat FeatureEngineer).
# Tidak ada 'id' -- skema telco_customers_synthetic tidak punya kolom itu,
# primary key-nya `synthetic_id` bukan tanggung jawab modul ini untuk di-drop.
DROP_COLS = ["gender", "total_charges"]

# Kolom numerik sebelum feature engineering.
NUMERIC_COLS = ["tenure", "monthly_charges"]

# Kolom add-on untuk service_count & has_any_addon.
ADDON_COLS = [
    "online_security",
    "online_backup",
    "device_protection",
    "tech_support",
    "streaming_tv",
    "streaming_movies",
]

# Kolom dengan structural dependency: addon (No internet service -> -1) + multiple_lines (No phone service -> -1).
STRUCTURAL_COLS = ADDON_COLS + ["multiple_lines"]

# Kolom binary Yes/No -> 1/0.
BINARY_COLS = ["partner", "dependents", "phone_service", "paperless_billing"]

# Kolom nominal untuk One-Hot Encoding (tenure_group ditambahkan terpisah di OHEWrapper
# karena baru ada setelah FeatureEngineer berjalan).
OHE_COLS = ["contract", "internet_service", "payment_method"]

# Kolom numerik kontinu yang di-scale StandardScaler (tenure, monthly_charges + 2 fitur
# hasil FeatureEngineer).
NUMERIC_TARGET_COLS = ["tenure", "monthly_charges", "tc_residual", "monthly_to_total_ratio"]

# tenure_group -- boundary data-driven, identik notebook asli (nilai numerik, bukan nama kolom).
TENURE_BINS = [0, 2, 18, 44, 72]
TENURE_LABELS = ["G1_0_2", "G2_2_18", "G3_18_44", "G4_44_72"]

# Payment method yang dianggap otomatis (nilai kategori, bukan nama kolom -- tidak berubah).
AUTO_PAYMENT_METHODS = [
    "Bank transfer (automatic)",
    "Credit card (automatic)",
]
