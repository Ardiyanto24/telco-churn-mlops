"""Bangun bundle (preprocessor+model+threshold) dan registrasikan/muat dari
MLflow Model Registry berdasarkan versi -- Milestone 1.5.

``build_bundle()`` memanggil ulang mekanisme grafting M1.2
(``churn_prediction.transform.artifact_loader``) -- lihat
milestones/1.5-inference-service/decisions.md Keputusan #6.

Registry di sini LOKAL/uji milik Milestone 1.5 (``constants.get_tracking_uri()``,
default ``sqlite:///mlruns.db``) -- registrasi resmi "versi produksi awal" tetap
Milestone 2.1, lihat Keputusan #1/#2/#7.
"""

import tempfile
import warnings
from pathlib import Path
from typing import Optional

import joblib
import mlflow
import mlflow.pyfunc

from ..transform.artifact_loader import DEFAULT_PREPROCESSOR_PATH, load_fitted_pipeline
from . import constants
from .pyfunc_model import ChurnPyfuncModel

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_PATH = _REPO_ROOT / "artifacs" / "model" / "model_final.joblib"


def build_bundle(
    threshold: float = constants.THRESHOLD,
    model_path: Path = DEFAULT_MODEL_PATH,
    preprocessor_path: Path = DEFAULT_PREPROCESSOR_PATH,
) -> dict:
    """Bangun dict bundle ``{"pipeline", "model", "threshold"}`` siap dipakai
    ``ChurnPyfuncModel``/``register_model()``.

    ``model_path`` dimuat apa adanya (``joblib.load``) -- BEDA dari
    ``preprocessor_path`` yang butuh shim+graft (``load_fitted_pipeline``)
    karena ``model_final.joblib`` (``VotingClassifier`` sklearn standar,
    berisi ``LGBMClassifier``+``XGBClassifier``) tidak memakai class custom
    notebook seperti preprocessor.
    """
    pipeline = load_fitted_pipeline(preprocessor_path)
    with warnings.catch_warnings():
        # UserWarning dari xgboost ("loading a serialized model ... generated
        # by an older version") -- versi training asli belum terkonfirmasi
        # (KT-3, docs/keputusan-tertunda.md), tapi predict_proba() terverifikasi
        # menghasilkan output valid (non-NaN) meski warning ini muncul.
        warnings.simplefilter("ignore")
        model = joblib.load(model_path)
    return {"pipeline": pipeline, "model": model, "threshold": threshold}


def register_model(bundle: dict, tracking_uri: Optional[str] = None):
    """Log ``bundle`` sebagai ``ChurnPyfuncModel`` dan registrasikan versi baru
    ke ``constants.MODEL_NAME`` di tracking URI yang diberikan (default
    ``constants.get_tracking_uri()``). Mengembalikan ``ModelInfo`` (punya
    ``.registered_model_version``).
    """
    mlflow.set_tracking_uri(tracking_uri or constants.get_tracking_uri())
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.joblib"
        joblib.dump(bundle, bundle_path)
        with mlflow.start_run():
            model_info = mlflow.pyfunc.log_model(
                name="model",
                python_model=ChurnPyfuncModel(),
                artifacts={"bundle": str(bundle_path)},
                registered_model_name=constants.MODEL_NAME,
            )
    return model_info


def load_model_by_version(version: str, tracking_uri: Optional[str] = None):
    """Muat versi ``version`` dari ``constants.MODEL_NAME`` -- BUKAN path file
    statis, sesuai KK M1.5 (mekanisme pemuatan model berdasarkan versi)."""
    mlflow.set_tracking_uri(tracking_uri or constants.get_tracking_uri())
    return mlflow.pyfunc.load_model(f"models:/{constants.MODEL_NAME}/{version}")
