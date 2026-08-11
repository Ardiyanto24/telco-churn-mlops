"""PreprocessingPipeline -- port 1:1 dari ``tccp-preprocessing-v2.ipynb`` cell 13.

DataSplitter (cell 14 notebook) SENGAJA tidak diport ke sini -- lihat
milestones/1.2-modularisasi-preprocessing/decisions.md Keputusan #3. Split
train/val/test adalah kebutuhan training, bukan kebutuhan jalur serving yang
dikonsumsi modul ini.
"""

from sklearn.base import BaseEstimator, TransformerMixin

from .binary_encoder import BinaryEncoder
from .column_dropper import ColumnDropper
from .feature_engineer import FeatureEngineer
from .ohe_wrapper import OHEWrapper
from .scaler_wrapper import ScalerWrapper
from .structural_encoder import StructuralEncoder

from . import constants


class PreprocessingPipeline(BaseEstimator, TransformerMixin):
    """Pipeline preprocessing end-to-end -- orkestrasi 6 step dalam urutan yang benar.

    Urutan step (KRITIS -- tidak boleh diubah, docs/03-notebook-audit/notebook-audit.md
    Bagian B):
      1. FeatureEngineer
         tc_residual dan monthly_to_total_ratio HARUS dihitung sebelum
         total_charges di-drop di step berikutnya.
      2. ColumnDropper
         Drop gender, total_charges SETELAH feature engineering selesai.
      3. StructuralEncoder
         Encode No internet/phone service -> -1 SEBELUM BinaryEncoder agar
         nilai 'No' biasa tidak tertimpa.
      4. BinaryEncoder
         Encode Yes/No -> 1/0 untuk kolom binary.
      5. OHEWrapper
         One-Hot Encoding untuk contract, internet_service, payment_method,
         dan tenure_group (dibuat di step 1).
      6. ScalerWrapper
         StandardScaler untuk tenure, monthly_charges, tc_residual,
         monthly_to_total_ratio.

    Prinsip:
      - fit() hanya boleh dipanggil pada training data (no leakage)
      - transform() dipanggil pada data lain memakai parameter dari fit()
      - Semua step sklearn-compatible -> serializable via joblib

    Input: DataFrame skema telco_customers_synthetic, 19 kolom FITUR snake_case
    (lihat docs/03-notebook-audit/notebook-audit.md Bagian H.3 -- 20 kolom bisnis
    dikurangi target `churn`, dan tanpa kolom metadata generator
    synthetic_id/generation_id/generated_at). Memproyeksikan kolom target dan
    metadata sebelum memanggil modul ini adalah tanggung jawab pemanggil,
    sama seperti notebook asli (`X_raw = df_raw.drop(columns=[TARGET])`
    dilakukan SEBELUM preprocessing pipeline dipanggil).

    Output: DataFrame 29 kolom numerik (docs/03-notebook-audit/notebook-audit.md
    Bagian C).
    """

    def __init__(self):
        self.feature_engineer_ = FeatureEngineer()
        self.col_dropper_ = ColumnDropper()
        self.structural_encoder_ = StructuralEncoder(cols=constants.STRUCTURAL_COLS)
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

    def get_feature_names(self):
        """Kembalikan nama fitur output setelah seluruh pipeline (post fit_transform)."""
        return list(self._last_output_columns_) if hasattr(self, "_last_output_columns_") else []
