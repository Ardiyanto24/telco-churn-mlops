"""Muat ``preprocessor.joblib`` asli DS dan "graft" parameter fitted-nya ke
``PreprocessingPipeline`` produksi (snake_case) -- Milestone 1.5.

Sentralisasi dari teknik yang awalnya cuma test-only scaffolding (Milestone 1.2
Checkpoint 5, lihat ``tests/transform/test_parity_real_artifact.py``). Sekarang
dipakai juga oleh jalur PRODUKSI (``churn_prediction.inference.registry``) untuk
membangun bundle model+preprocessor -- lihat
``milestones/1.5-inference-service/decisions.md`` Keputusan #6.

Strategi (identik M1.2 Keputusan #4):
1. Load ``preprocessor.joblib`` -- class-nya didefinisikan di kernel Kaggle asli
   (``__main__``), butuh shim ``sys.modules`` ke class referensi PascalCase
   (``_notebook_reference``, BUKAN class produksi -- lihat docstring modul itu
   kenapa shim ke class produksi akan diam-diam salah).
2. "Graft" parameter fitted (``StandardScaler.mean_``/``scale_``,
   ``OneHotEncoder.categories_``) dari objek asli ke instance
   ``PreprocessingPipeline`` kita -- skip ``fit()``, langsung siap ``transform()``.
   Valid karena parameter ini berbasis urutan POSISI kolom, bukan nama kolom.
"""

import copy
import sys
import warnings
from pathlib import Path

import joblib

from . import _notebook_reference as ref
from . import constants
from .pipeline import PreprocessingPipeline

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PREPROCESSOR_PATH = _REPO_ROOT / "artifacs" / "proprocessor" / "preprocessor.joblib"


def load_original_preprocessor(preprocessor_path: Path = DEFAULT_PREPROCESSOR_PATH):
    """Load ``preprocessor.joblib`` asli (PascalCase, class referensi) apa adanya --
    TANPA graft. Dipakai sebagai ground truth KK2 (bandingkan terhadap pipeline
    ter-graft dari ``load_fitted_pipeline()``), lihat
    ``tests/transform/test_parity_real_artifact.py``.
    """
    main_mod = sys.modules["__main__"]
    for cls in [
        ref.PreprocessingPipeline,
        ref.FeatureEngineer,
        ref.ColumnDropper,
        ref.StructuralEncoder,
        ref.BinaryEncoder,
        ref.OHEWrapper,
        ref.ScalerWrapper,
    ]:
        setattr(main_mod, cls.__name__, cls)

    with warnings.catch_warnings():
        # InconsistentVersionWarning: artifact di-fit dengan scikit-learn 1.6.1
        # (versi yang sudah dikunci M1.2 Checkpoint 6 -- bukan mismatch nyata).
        warnings.simplefilter("ignore")
        return joblib.load(preprocessor_path)


def _graft_pipeline(real_obj) -> PreprocessingPipeline:
    """Suntikkan parameter fitted dari objek asli ke instance produksi kita.

    Deep-copy dulu supaya tidak memutasi ``real_obj``. ``feature_names_in_``
    dihapus dari salinan encoder/scaler kita -- sklearn modern memvalidasi
    nama kolom persis terhadap yang dilihat saat fit (PascalCase), padahal
    grafting ini seharusnya posisi-based, bukan nama-based.
    """
    mine = PreprocessingPipeline()

    mine.structural_encoder_.cols_present_ = list(constants.STRUCTURAL_COLS)
    mine.binary_encoder_.cols_present_ = list(constants.BINARY_COLS)
    mine.col_dropper_.cols_dropped_ = list(constants.DROP_COLS)

    mine.ohe_wrapper_.cols_present_ = list(constants.OHE_COLS) + ["tenure_group"]
    mine.ohe_wrapper_._encoder = copy.deepcopy(real_obj.ohe_wrapper_._encoder)
    if hasattr(mine.ohe_wrapper_._encoder, "feature_names_in_"):
        del mine.ohe_wrapper_._encoder.feature_names_in_
    # Tidak pakai encoder.get_feature_names_out(cols) -- encoder mengingat
    # feature_names_in_ dari fit asli (PascalCase) dan menolak nama snake_case
    # kita. Bangun nama manual dari categories_/drop_idx_ (posisi-based).
    names = []
    for col, cats, didx in zip(
        mine.ohe_wrapper_.cols_present_,
        mine.ohe_wrapper_._encoder.categories_,
        mine.ohe_wrapper_._encoder.drop_idx_,
    ):
        surviving = [c for i, c in enumerate(cats) if i != didx]
        names.extend(f"{col}_{c}" for c in surviving)
    mine.ohe_wrapper_.ohe_feature_names_ = names

    mine.scaler_wrapper_.cols_present_ = list(constants.NUMERIC_TARGET_COLS)
    mine.scaler_wrapper_._scaler = copy.deepcopy(real_obj.scaler_wrapper_._scaler)
    if hasattr(mine.scaler_wrapper_._scaler, "feature_names_in_"):
        del mine.scaler_wrapper_._scaler.feature_names_in_

    return mine


def load_fitted_pipeline(preprocessor_path: Path = DEFAULT_PREPROCESSOR_PATH) -> PreprocessingPipeline:
    """Muat ``preprocessor.joblib`` asli dan kembalikan ``PreprocessingPipeline``
    produksi (snake_case) yang parameternya sudah di-graft -- siap ``transform()``
    tanpa perlu ``fit()`` ulang.
    """
    real_obj = load_original_preprocessor(preprocessor_path)
    return _graft_pipeline(real_obj)
