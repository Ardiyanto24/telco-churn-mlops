"""BinaryEncoder -- port 1:1 dari ``tccp-preprocessing-v2.ipynb`` cell 10."""

from sklearn.base import BaseEstimator, TransformerMixin

from . import constants


class BinaryEncoder(BaseEstimator, TransformerMixin):
    """Encode kolom binary Yes/No menjadi 1/0.

    Kolom yang di-encode (constants.BINARY_COLS): partner, dependents,
    phone_service, paperless_billing -> Yes=1, No=0.

    Tidak di-encode: gender (di-drop sebelum langkah ini oleh ColumnDropper),
    senior_citizen (sudah int 0/1 dari sumber, tidak disentuh untuk menghindari
    double-encode).

    Input: DataFrame dengan kolom di BINARY_COLS bernilai 'Yes'/'No'.
    Output: kolom yang sama bernilai 1/0.
    """

    BINARY_MAP = {"Yes": 1, "No": 0}

    def __init__(self, cols: list = None):
        self.cols = cols or constants.BINARY_COLS

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
