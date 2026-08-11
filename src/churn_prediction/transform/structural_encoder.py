"""StructuralEncoder -- port 1:1 dari ``tccp-preprocessing-v2.ipynb`` cell 7."""

from sklearn.base import BaseEstimator, TransformerMixin


class StructuralEncoder(BaseEstimator, TransformerMixin):
    """Encode 3 level semantik pada kolom add-on dan multiple_lines.

    Input yang diharapkan: DataFrame dengan kolom-kolom yang disebut di ``cols``
    (default: ``constants.STRUCTURAL_COLS``) bernilai salah satu dari
    ``'Yes'``, ``'No'``, ``'No internet service'``, ``'No phone service'``.

    Output: kolom yang sama, nilainya diganti:
      'Yes'                 ->  1  (aktif -- punya akses dan ambil layanan)
      'No'                  ->  0  (tidak aktif -- punya akses tapi tidak ambil)
      'No internet service' -> -1  (tidak relevan -- tidak punya internet)
      'No phone service'    -> -1  (tidak relevan -- tidak punya telepon)

    Mengapa -1, bukan 0: kalau 'No' dan 'No internet service' keduanya jadi 0,
    model kehilangan informasi struktural bahwa pelanggan tanpa internet secara
    definitif tidak bisa punya add-on -- bukan pilihan, tapi constraint.

    Fitur yang diproduksi: nilai numerik untuk online_security, online_backup,
    device_protection, tech_support, streaming_tv, streaming_movies, multiple_lines
    (lihat docs/03-notebook-audit/notebook-audit.md Bagian C.4).
    """

    STRUCTURAL_MAP = {
        "Yes": 1,
        "No": 0,
        "No internet service": -1,
        "No phone service": -1,
    }

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
