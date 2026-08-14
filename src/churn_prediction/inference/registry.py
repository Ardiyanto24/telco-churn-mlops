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

import os
import tempfile
import warnings
from pathlib import Path
from typing import Optional

import boto3
import joblib
import mlflow
import mlflow.pyfunc
import mlflow.tracking
import yaml

from ..transform.artifact_loader import DEFAULT_PREPROCESSOR_PATH, load_fitted_pipeline
from . import constants
from .artifact_validation import sanity_check_bundle
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


def _fix_windows_artifact_paths(model_id: str, run_id: str) -> None:
    """Post-process manifest ``MLmodel`` di S3 -- normalisasi backslash jadi
    forward-slash pada field ``flavors.python_function.artifacts.*.path``.

    Root cause SEBENARNYA dari bug lintas-platform Windows->Linux (BEDA dari
    diagnosis awal Milestone 2.5, ``bundle_path.as_posix()`` di bawah TIDAK
    cukup): ``mlflow.pyfunc.log_model()`` sendiri (``mlflow/pyfunc/model.py``,
    fungsi internal penyimpan ``artifacts={}``) memakai ``os.path.join()``
    untuk membangun field ``path`` tiap entry artifacts -- di Windows ini
    SELALU menghasilkan backslash, TERLEPAS dari apakah source path yang
    diberikan caller (``bundle_path.as_posix()`` vs ``str(bundle_path)``)
    posix atau native. Field ``path`` inilah yang dipakai
    ``context.artifacts[key]`` saat ``load_context()`` -- backslash di sini
    membuat ``os.path.join`` di Linux menghasilkan nama file literal dengan
    backslash yang tidak pernah ada di filesystem (``FileNotFoundError``).

    Dibuktikan ditemukan Milestone 3.4: 2 versi kandidat baru yang
    diregistrasi ulang dari mesin dev Windows yang sama (versi 3, dengan
    ``.as_posix()``; percobaan dengan ``str(bundle_path)`` malah merusak
    upload artifact sepenuhnya) SAMA-SAMA gagal dimuat dari Linux dengan
    ``FileNotFoundError`` identik -- dikonfirmasi lewat perbandingan manifest
    ``MLmodel`` byte-per-byte versi yang bekerja (field ``path`` forward-slash,
    kebetulan/historis) vs versi baru yang gagal (field ``path`` backslash).
    Lihat milestones/3.4-deteksi-versi-model-aktif/decisions.md.

    Cuma berlaku untuk artifact store S3 (registry produksi, Milestone 2.1) --
    di-skip (bukan error) kalau run ini memakai artifact store lokal/lainnya
    (mis. test suite yang sengaja pakai tracking URI SQLite terisolasi,
    `tests/inference/test_registry.py` -- di situ register+load SELALU di
    OS yang sama, backslash tidak pernah jadi masalah). Dicek dari
    `artifact_uri` run yang BARU SAJA dibuat, bukan dari ada/tidaknya env var
    S3 (env var bisa saja tersedia di environment meski run ini tidak
    memakainya).
    """
    artifact_uri = mlflow.tracking.MlflowClient().get_run(run_id).info.artifact_uri
    if not artifact_uri.startswith("s3://"):
        return

    bucket = os.environ["MLFLOW_ARTIFACT_BUCKET"]
    key = f"models/{model_id}/artifacts/MLmodel"
    s3 = boto3.client("s3", endpoint_url=os.environ.get("MLFLOW_S3_ENDPOINT_URL"))

    raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    manifest = yaml.safe_load(raw)

    artifacts = manifest.get("flavors", {}).get("python_function", {}).get("artifacts", {})
    changed = False
    for entry in artifacts.values():
        path = entry.get("path", "")
        if "\\" in path:
            entry["path"] = path.replace("\\", "/")
            changed = True

    if changed:
        fixed = yaml.safe_dump(manifest, default_flow_style=False, sort_keys=False)
        s3.put_object(Bucket=bucket, Key=key, Body=fixed.encode("utf-8"))


def register_model(bundle: dict, tracking_uri: Optional[str] = None):
    """Log ``bundle`` sebagai ``ChurnPyfuncModel`` dan registrasikan versi baru
    ke ``constants.MODEL_NAME`` di tracking URI yang diberikan (default
    ``constants.get_tracking_uri()``). Mengembalikan ``ModelInfo`` (punya
    ``.registered_model_version``).

    ``bundle_path.as_posix()`` dipakai untuk source path lokal (kebersihan
    umum), TAPI perbaikan UTAMA lintas-platform ada di
    ``_fix_windows_artifact_paths()`` (dipanggil di akhir fungsi ini) --
    lihat docstring fungsi itu untuk root cause lengkap (diagnosis Milestone
    2.5 soal ``.as_posix()`` TERNYATA tidak menutup bug ini, ditemukan ulang
    Milestone 3.4).

    Gerbang sanity check (Milestone 2.8, Bagian 5.5 dokumen arsitektur)
    dijalankan DI SINI -- di dalam ``register_model()``, bukan cuma di script
    pemanggil -- supaya SETIAP jalur registrasi otomatis terlindungi.
    ``ValueError`` di-raise SEBELUM ``mlflow.pyfunc.log_model()`` dipanggil
    kalau gagal -- artifact rusak tidak pernah ter-log/registrasi sama sekali.
    """
    sanity = sanity_check_bundle(bundle)
    if not sanity.passed:
        raise ValueError(
            "Bundle gagal sanity check, TIDAK diregistrasi: " + "; ".join(sanity.failures)
        )

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
    _fix_windows_artifact_paths(model_info.model_uuid, model_info.run_id)
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
