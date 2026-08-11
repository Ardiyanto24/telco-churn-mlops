"""Transkripsi literal (PascalCase, TEST-ONLY) dari kelas asli
``tccp-preprocessing-v2.ipynb`` cell 7-13 -- BUKAN bagian modul produksi.

Kenapa file ini ada: ``joblib.load()`` pada ``preprocessor.joblib`` hanya
memulihkan ATRIBUT (``__dict__``) instance, bukan KODE method -- begitu
di-unpickle, method yang benar-benar jalan adalah method dari class yang
terdaftar di ``sys.modules`` saat load, bukan kode asli notebook. Modul
produksi kita (``churn_prediction.transform.*``) memakai literal kolom
snake_case, jadi kalau artifact di-shim ke class produksi lalu ``.transform()``
dipanggil pada DataFrame PascalCase asli, kondisi ``if 'total_charges' in
X.columns`` akan False terus (kolom aslinya "TotalCharges") -- fitur seperti
``monthly_to_total_ratio``/``is_auto_payment`` diam-diam tidak pernah dibuat.

File ini menyediakan class dengan literal PascalCase asli supaya artifact
bisa di-unpickle dan di-``transform()`` dengan benar sebagai ground truth
KK2 (dibandingkan terhadap docs/03-notebook-audit/notebook-audit.md Bagian B-C
yang ditranskrip dari cell yang sama).
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DROP_COLS = ["id", "gender", "TotalCharges"]
ADDON_COLS = [
    "OnlineSecurity", "OnlineBackup", "DeviceProtection",
    "TechSupport", "StreamingTV", "StreamingMovies",
]
STRUCTURAL_COLS = ADDON_COLS + ["MultipleLines"]
BINARY_COLS = ["Partner", "Dependents", "PhoneService", "PaperlessBilling"]
OHE_COLS = ["Contract", "InternetService", "PaymentMethod"]
TENURE_BINS = [0, 2, 18, 44, 72]
TENURE_LABELS = ["G1_0_2", "G2_2_18", "G3_18_44", "G4_44_72"]
AUTO_PAYMENT_METHODS = ["Bank transfer (automatic)", "Credit card (automatic)"]


class StructuralEncoder(BaseEstimator, TransformerMixin):
    STRUCTURAL_MAP = {"Yes": 1, "No": 0, "No internet service": -1, "No phone service": -1}

    def __init__(self, cols: list = None):
        self.cols = cols

    def fit(self, X, y=None):
        self.cols_present_ = [c for c in (self.cols or []) if c in X.columns]
        return self

    def transform(self, X):
        X = X.copy()
        for col in self.cols_present_:
            X[col] = X[col].map(self.STRUCTURAL_MAP).fillna(X[col])
        return X

    def get_feature_names_out(self, input_features=None):
        return input_features


class FeatureEngineer(BaseEstimator, TransformerMixin):
    def __init__(self, tenure_bins=None, tenure_labels=None, addon_cols=None, auto_methods=None):
        self.tenure_bins = tenure_bins or TENURE_BINS
        self.tenure_labels = tenure_labels or TENURE_LABELS
        self.addon_cols = addon_cols or ADDON_COLS
        self.auto_methods = auto_methods or AUTO_PAYMENT_METHODS

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = X.copy()
        if "TotalCharges" in X.columns and "tenure" in X.columns and "MonthlyCharges" in X.columns:
            computed_total = X["tenure"] * X["MonthlyCharges"]
            X["tc_residual"] = X["TotalCharges"] - computed_total
        else:
            X["tc_residual"] = 0.0

        if "TotalCharges" in X.columns and "MonthlyCharges" in X.columns:
            total_safe = X["TotalCharges"].replace(0, np.nan)
            X["monthly_to_total_ratio"] = (X["MonthlyCharges"] / total_safe).fillna(1.0)

        if "tenure" in X.columns:
            X["tenure_group"] = pd.cut(
                X["tenure"], bins=self.tenure_bins, labels=self.tenure_labels, include_lowest=True
            ).astype(str)

        if "PaymentMethod" in X.columns:
            X["is_auto_payment"] = X["PaymentMethod"].isin(self.auto_methods).astype(int)

        addon_present = [c for c in self.addon_cols if c in X.columns]
        if addon_present:
            X["service_count"] = X[addon_present].apply(lambda row: (row == "Yes").sum(), axis=1).astype(int)

        if "service_count" in X.columns:
            X["has_any_addon"] = (X["service_count"] > 0).astype(int)

        return X

    def get_feature_names_out(self, input_features=None):
        return input_features


class ColumnDropper(BaseEstimator, TransformerMixin):
    def __init__(self, cols_to_drop: list = None):
        self.cols_to_drop = cols_to_drop or DROP_COLS

    def fit(self, X, y=None):
        self.cols_dropped_ = [c for c in self.cols_to_drop if c in X.columns]
        self.cols_missing_ = [c for c in self.cols_to_drop if c not in X.columns]
        return self

    def transform(self, X):
        return X.drop(columns=self.cols_dropped_, errors="ignore")

    def get_feature_names_out(self, input_features=None):
        if input_features is None:
            return None
        return [f for f in input_features if f not in self.cols_dropped_]


class BinaryEncoder(BaseEstimator, TransformerMixin):
    BINARY_MAP = {"Yes": 1, "No": 0}

    def __init__(self, cols: list = None):
        self.cols = cols or BINARY_COLS

    def fit(self, X, y=None):
        self.cols_present_ = [c for c in self.cols if c in X.columns]
        return self

    def transform(self, X):
        X = X.copy()
        for col in self.cols_present_:
            X[col] = X[col].map(self.BINARY_MAP).fillna(X[col])
        return X

    def get_feature_names_out(self, input_features=None):
        return input_features


class OHEWrapper(BaseEstimator, TransformerMixin):
    def __init__(self, cols: list = None):
        self.cols = cols or (OHE_COLS + ["tenure_group"])
        self._encoder = OneHotEncoder(drop="first", sparse_output=False, handle_unknown="ignore", dtype=np.float64)

    def fit(self, X, y=None):
        self.cols_present_ = [c for c in self.cols if c in X.columns]
        if self.cols_present_:
            self._encoder.fit(X[self.cols_present_])
            self.ohe_feature_names_ = self._encoder.get_feature_names_out(self.cols_present_).tolist()
        else:
            self.ohe_feature_names_ = []
        return self

    def transform(self, X):
        X = X.copy()
        if not self.cols_present_:
            return X
        ohe_array = self._encoder.transform(X[self.cols_present_])
        ohe_df = pd.DataFrame(ohe_array, columns=self.ohe_feature_names_, index=X.index)
        X = X.drop(columns=self.cols_present_)
        X = pd.concat([X, ohe_df], axis=1)
        return X

    def get_feature_names_out(self, input_features=None):
        return input_features


class ScalerWrapper(BaseEstimator, TransformerMixin):
    NUMERIC_TARGET_COLS = ["tenure", "MonthlyCharges", "tc_residual", "monthly_to_total_ratio"]

    def __init__(self, cols: list = None):
        self.cols = cols or self.NUMERIC_TARGET_COLS
        self._scaler = StandardScaler()

    def fit(self, X, y=None):
        self.cols_present_ = [c for c in self.cols if c in X.columns]
        if self.cols_present_:
            self._scaler.fit(X[self.cols_present_])
        return self

    def transform(self, X):
        X = X.copy()
        if self.cols_present_:
            X[self.cols_present_] = self._scaler.transform(X[self.cols_present_])
        return X

    def get_feature_names_out(self, input_features=None):
        return input_features


class PreprocessingPipeline(BaseEstimator, TransformerMixin):
    def __init__(self):
        self.feature_engineer_ = FeatureEngineer()
        self.col_dropper_ = ColumnDropper()
        self.structural_encoder_ = StructuralEncoder(cols=STRUCTURAL_COLS)
        self.binary_encoder_ = BinaryEncoder()
        self.ohe_wrapper_ = OHEWrapper()
        self.scaler_wrapper_ = ScalerWrapper()
        self._steps = [
            ("feature_engineer", self.feature_engineer_),
            ("col_dropper", self.col_dropper_),
            ("structural_encoder", self.structural_encoder_),
            ("binary_encoder", self.binary_encoder_),
            ("ohe_wrapper", self.ohe_wrapper_),
            ("scaler_wrapper", self.scaler_wrapper_),
        ]

    def fit(self, X, y=None):
        self.fit_transform(X, y)
        return self

    def fit_transform(self, X, y=None):
        X_transformed = X.copy()
        for _, step in self._steps:
            X_transformed = step.fit_transform(X_transformed, y)
        self._last_output_columns_ = X_transformed.columns.tolist()
        return X_transformed

    def transform(self, X):
        X_transformed = X.copy()
        for _, step in self._steps:
            X_transformed = step.transform(X_transformed)
        return X_transformed
