"""OHEWrapper -- port 1:1 dari ``tccp-preprocessing-v2.ipynb`` cell 11.

PENTING (Keputusan #4, milestones/1.2-modularisasi-preprocessing/decisions.md):
``sklearn.OneHotEncoder`` menyimpan ``categories_`` berbasis urutan POSISI kolom
saat fit, bukan nama kolom -- urutan default ``cols`` di sini (``contract``,
``internet_service``, ``payment_method``, ``tenure_group``) harus tetap
persis sama posisinya dengan urutan asli notebook (``Contract``,
``InternetService``, ``PaymentMethod``, ``tenure_group``) supaya parameter
fitted dari ``preprocessor.joblib`` asli bisa di-graft ke instance ini.
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import OneHotEncoder

from . import constants


class OHEWrapper(BaseEstimator, TransformerMixin):
    """One-Hot Encoding untuk kolom nominal.

    Kolom yang di-OHE (default constants.OHE_COLS + ['tenure_group']):
      contract        -> 3 kategori, drop_first -> 2 dummy
      internet_service -> 3 kategori -> 2 dummy
      payment_method   -> 4 kategori -> 3 dummy
      tenure_group     -> 4 kategori (G1-G4, hasil FeatureEngineer) -> 3 dummy

    One-hot dipilih (bukan ordinal) karena jarak antar kategori tidak setara.
    ``handle_unknown='ignore'`` -- API real-time tidak boleh crash karena
    payload valid tapi berisi kategori baru yang belum pernah dilihat saat fit
    (prinsip Bagian 2 dokumen arsitektur).

    Input: DataFrame dengan kolom di `cols`. Output: kolom asli diganti kolom
    dummy hasil OHE (10 kolom total lintas 4 sumber, lihat
    docs/03-notebook-audit/notebook-audit.md Bagian C.5).
    """

    def __init__(self, cols: list = None):
        self.cols = cols or (constants.OHE_COLS + ["tenure_group"])
        self._encoder = OneHotEncoder(
            drop="first",
            sparse_output=False,
            handle_unknown="ignore",
            dtype=np.float64,
        )

    def fit(self, X, y=None):
        self.cols_present_ = [c for c in self.cols if c in X.columns]
        if self.cols_present_:
            self._encoder.fit(X[self.cols_present_])
            self.ohe_feature_names_ = self._encoder.get_feature_names_out(
                self.cols_present_
            ).tolist()
        else:
            self.ohe_feature_names_ = []
        return self

    def transform(self, X):
        X = X.copy()
        if not self.cols_present_:
            return X

        ohe_array = self._encoder.transform(X[self.cols_present_])
        ohe_df = pd.DataFrame(
            ohe_array,
            columns=self.ohe_feature_names_,
            index=X.index,
        )
        X = X.drop(columns=self.cols_present_)
        X = pd.concat([X, ohe_df], axis=1)
        return X

    def get_feature_names_out(self, input_features=None):
        return input_features
