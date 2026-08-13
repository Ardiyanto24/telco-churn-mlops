"""Bangun bundle (preprocessor+model+threshold) dan registrasikan/muat dari
MLflow Model Registry berdasarkan versi ATAU alias -- Milestone 1.5 (versi
eksplisit) + Milestone 2.1 (alias "versi aktif").

``build_bundle()`` memanggil ulang mekanisme grafting M1.2
(``churn_prediction.transform.artifact_loader``) -- lihat
milestones/1.5-inference-service/decisions.md Keputusan #6.

``constants.get_tracking_uri()`` menunjuk ke registry resmi sejak Milestone 2.1
(direct-access Postgres Supabase, TANPA proses `mlflow server`) -- default
``sqlite:///mlruns.db`` (pola M1.5) hanya dipakai kalau env var
``MLFLOW_TRACKING_URI`` tidak diset (mis. dev lokal tanpa akses Supabase). Lihat
milestones/2.1-fondasi-orchestrator-model-registry/decisions.md Keputusan #2.
"""

import tempfile
import warnings
from pathlib import Path
from typing import Optional

import joblib
import mlflow
import mlflow.pyfunc
import mlflow.tracking

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

    ``bundle_path.as_posix()`` (BUKAN ``str(bundle_path)``) -- mitigasi bug
    upstream MLflow (https://github.com/mlflow/mlflow/issues/11862): saat
    ``artifacts={}`` di-log dari Windows, MLflow menyimpan path relatif
    artifact APA ADANYA (termasuk backslash Windows) ke manifest ``MLmodel``,
    yang lalu gagal di-resolve saat model dimuat dari Linux (mis. Prefect
    Managed, ditemukan Milestone 2.5 Checkpoint 3 -- lihat
    milestones/2.5-batch-scoring-dag/decisions.md). ``.as_posix()`` memaksa
    forward-slash terlepas dari OS tempat registrasi dijalankan -- mitigasi
    best-effort, BELUM diverifikasi menutup bug upstream 100% untuk semua
    kasus (registrasi versi berikutnya WAJIB diverifikasi ulang lintas-OS,
    bukan diasumsikan aman).
    """
    mlflow.set_tracking_uri(tracking_uri or constants.get_tracking_uri())
    with tempfile.TemporaryDirectory() as tmp_dir:
        bundle_path = Path(tmp_dir) / "bundle.joblib"
        joblib.dump(bundle, bundle_path)
        with mlflow.start_run():
            model_info = mlflow.pyfunc.log_model(
                name="model",
                python_model=ChurnPyfuncModel(),
                artifacts={"bundle": bundle_path.as_posix()},
                registered_model_name=constants.MODEL_NAME,
            )
    return model_info


def load_model_by_version(version: str, tracking_uri: Optional[str] = None):
    """Muat versi ``version`` dari ``constants.MODEL_NAME`` -- BUKAN path file
    statis, sesuai KK M1.5 (mekanisme pemuatan model berdasarkan versi)."""
    mlflow.set_tracking_uri(tracking_uri or constants.get_tracking_uri())
    return mlflow.pyfunc.load_model(f"models:/{constants.MODEL_NAME}/{version}")


def set_active_alias(version: str, alias: str = constants.ACTIVE_ALIAS, tracking_uri: Optional[str] = None):
    """Tandai ``version`` sebagai versi aktif lewat MLflow Model Registry Alias
    (default ``champion``) -- konvensi versi aktif Milestone 2.1, dipakai
    bersama batch DAG dan real-time API. Menggantikan Stage (deprecated di
    MLflow). Lihat milestones/2.1-fondasi-orchestrator-model-registry/
    decisions.md Keputusan #5.
    """
    mlflow.set_tracking_uri(tracking_uri or constants.get_tracking_uri())
    client = mlflow.tracking.MlflowClient()
    client.set_registered_model_alias(constants.MODEL_NAME, alias, version)


def load_active_model(alias: str = constants.ACTIVE_ALIAS, tracking_uri: Optional[str] = None):
    """Muat model yang ditandai ``alias`` (default ``champion``) -- mekanisme
    pemuatan "versi aktif" TANPA hardcode nomor versi, pelengkap
    ``load_model_by_version()`` (tetap berguna untuk pin ke versi eksplisit,
    mis. verifikasi promosi Milestone 2.8)."""
    mlflow.set_tracking_uri(tracking_uri or constants.get_tracking_uri())
    return mlflow.pyfunc.load_model(f"models:/{constants.MODEL_NAME}@{alias}")


def resolve_alias_version(alias: str = constants.ACTIVE_ALIAS, tracking_uri: Optional[str] = None) -> str:
    """Selesaikan ``alias`` (mis. ``champion``) ke nomor versi konkret saat ini
    -- Milestone 2.5. Dibutuhkan untuk lineage: alias bisa berpindah menunjuk
    versi lain di masa depan (Milestone 2.8), jadi baris hasil prediksi WAJIB
    mencatat nomor versi konkret yang benar-benar dipakai, bukan cuma nama
    alias yang mutable.
    """
    mlflow.set_tracking_uri(tracking_uri or constants.get_tracking_uri())
    client = mlflow.tracking.MlflowClient()
    return client.get_model_version_by_alias(constants.MODEL_NAME, alias).version
