"""ColumnDropper -- port 1:1 dari ``tccp-preprocessing-v2.ipynb`` cell 9."""

from sklearn.base import BaseEstimator, TransformerMixin

from . import constants


class ColumnDropper(BaseEstimator, TransformerMixin):
    """Drop kolom yang sudah diputuskan tidak digunakan sebagai fitur.

    Kolom yang di-drop (constants.DROP_COLS): gender, total_charges.
    (Notebook asli juga men-drop `id` -- tidak relevan di sini karena skema
    telco_customers_synthetic tidak punya kolom itu, lihat Keputusan #1.)

    Drop dilakukan SETELAH feature engineering agar tc_residual dan
    monthly_to_total_ratio bisa memanfaatkan total_charges terlebih dahulu.

    Input: DataFrame apa pun. Output: DataFrame tanpa kolom di DROP_COLS,
    kolom yang sudah tidak ada diabaikan (tidak error).
    """

    def __init__(self, cols_to_drop: list = None):
        self.cols_to_drop = cols_to_drop or constants.DROP_COLS

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
