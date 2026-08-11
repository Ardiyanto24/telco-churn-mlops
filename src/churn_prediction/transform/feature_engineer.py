"""FeatureEngineer -- port 1:1 dari ``tccp-preprocessing-v2.ipynb`` cell 8.

Nama kolom input snake_case (Keputusan #1) -- nama fitur turunan yang
diproduksi TIDAK berubah (sudah snake_case/lowercase di notebook asli).
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from . import constants


class FeatureEngineer(BaseEstimator, TransformerMixin):
    """Membuat 6 fitur baru berdasarkan bukti kuantitatif EDA (lihat
    docs/03-notebook-audit/notebook-audit.md Bagian C.1-C.3 untuk formula lengkap).

    Urutan pembuatan KRITIS -- beberapa fitur bergantung pada kolom asli yang
    akan di-drop atau di-encode di step berikutnya (ColumnDropper, OHEWrapper):

    1. tc_residual (butuh total_charges SEBELUM di-drop)
       = total_charges - (tenure x monthly_charges)
    2. monthly_to_total_ratio (butuh total_charges SEBELUM di-drop)
       = monthly_charges / total_charges (0 -> NaN -> fillna(1.0))
    3. tenure_group (boundary data-driven constants.TENURE_BINS)
    4. is_auto_payment (butuh payment_method SEBELUM di-OHE)
    5. service_count (KONDISIONAL -- hitung hanya nilai 'Yes' di kolom addon)
    6. has_any_addon (KONDISIONAL -- derived dari service_count)

    Input yang diharapkan: DataFrame dengan kolom tenure, monthly_charges,
    total_charges, payment_method, dan kolom-kolom addon (constants.ADDON_COLS).

    Output: DataFrame input + 6 kolom baru di atas.
    """

    def __init__(
        self,
        tenure_bins: list = None,
        tenure_labels: list = None,
        addon_cols: list = None,
        auto_methods: list = None,
    ):
        self.tenure_bins = tenure_bins or constants.TENURE_BINS
        self.tenure_labels = tenure_labels or constants.TENURE_LABELS
        self.addon_cols = addon_cols or constants.ADDON_COLS
        self.auto_methods = auto_methods or constants.AUTO_PAYMENT_METHODS

    def fit(self, X, y=None):
        # Semua transformasi deterministik -- tidak ada state yang perlu di-fit
        return self

    def transform(self, X):
        X = X.copy()

        # -- 1. tc_residual -- harus SEBELUM total_charges di-drop
        if "total_charges" in X.columns and "tenure" in X.columns and "monthly_charges" in X.columns:
            computed_total = X["tenure"] * X["monthly_charges"]
            X["tc_residual"] = X["total_charges"] - computed_total
        else:
            X["tc_residual"] = 0.0

        # -- 2. monthly_to_total_ratio -- harus SEBELUM total_charges di-drop
        if "total_charges" in X.columns and "monthly_charges" in X.columns:
            total_safe = X["total_charges"].replace(0, np.nan)
            X["monthly_to_total_ratio"] = (X["monthly_charges"] / total_safe).fillna(1.0)

        # -- 3. tenure_group (boundary data-driven) --
        if "tenure" in X.columns:
            X["tenure_group"] = pd.cut(
                X["tenure"],
                bins=self.tenure_bins,
                labels=self.tenure_labels,
                include_lowest=True,
            ).astype(str)

        # -- 4. is_auto_payment -- harus SEBELUM payment_method di-OHE
        if "payment_method" in X.columns:
            X["is_auto_payment"] = X["payment_method"].isin(self.auto_methods).astype(int)

        # -- 5. service_count (kondisional -- hanya hitung 'Yes') --
        addon_present = [c for c in self.addon_cols if c in X.columns]
        if addon_present:
            X["service_count"] = X[addon_present].apply(
                lambda row: (row == "Yes").sum(), axis=1
            ).astype(int)

        # -- 6. has_any_addon (kondisional -- derived dari service_count) --
        if "service_count" in X.columns:
            X["has_any_addon"] = (X["service_count"] > 0).astype(int)

        return X

    def get_feature_names_out(self, input_features=None):
        return input_features
