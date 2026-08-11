"""ScalerWrapper -- port 1:1 dari ``tccp-preprocessing-v2.ipynb`` cell 12.

PENTING (Keputusan #4, milestones/1.2-modularisasi-preprocessing/decisions.md):
``StandardScaler`` menyimpan ``mean_``/``scale_`` berbasis urutan POSISI kolom
saat fit -- urutan default ``constants.NUMERIC_TARGET_COLS`` harus tetap
persis sama posisinya dengan urutan asli notebook (``tenure``,
``MonthlyCharges``, ``tc_residual``, ``monthly_to_total_ratio``) supaya
parameter fitted dari ``preprocessor.joblib`` asli bisa di-graft ke instance ini.
"""

from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import StandardScaler

from . import constants


class ScalerWrapper(BaseEstimator, TransformerMixin):
    """StandardScaler (z-score) untuk fitur numerik kontinu.

    Kolom yang di-scale (constants.NUMERIC_TARGET_COLS): tenure,
    monthly_charges, tc_residual, monthly_to_total_ratio.

    Tidak di-scale (walaupun numerik): senior_citizen, is_auto_payment
    (binary 0/1), service_count (integer diskret), has_any_addon (binary),
    seluruh hasil OHE (binary 0/1).

    Input: DataFrame dengan kolom di NUMERIC_TARGET_COLS. Output: kolom yang
    sama, ter-scale (fit hanya boleh dipanggil pada training data).
    """

    def __init__(self, cols: list = None):
        self.cols = cols or constants.NUMERIC_TARGET_COLS
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
