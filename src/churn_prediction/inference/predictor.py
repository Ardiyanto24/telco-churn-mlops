"""API publik ``predict()``/``predict_active()`` -- titik masuk utama package
``churn_prediction.inference``, Milestone 1.5 (versi eksplisit) + Milestone
2.5 (alias "versi aktif", dipakai batch DAG).

Kontrak (milestones/1.5-inference-service/decisions.md Keputusan #3/#4):
    Input  : ``pandas.DataFrame`` (1+ baris), skema sama dengan
             ``churn_prediction.schema.raw_schema.RawDataSchema`` (19 kolom
             fitur snake_case). Validasi dijalankan DI DALAM fungsi ini --
             bukan diasumsikan sudah dilakukan pemanggil.
    Output : ``pandas.DataFrame`` (urutan baris = urutan input), kolom:
             ``churn_probability`` (float), ``churn_label`` (int 0/1, dari
             threshold yang tersimpan di bundle versi yang dimuat),
             ``model_version`` (str, NOMOR VERSI KONKRET -- lihat
             ``predict_active()``), ``predicted_at`` (ISO8601 UTC).

Data yang tidak lolos ``RawDataSchema`` menghasilkan error eksplisit
(``pandera.errors.SchemaError``/``SchemaErrors``) -- TIDAK PERNAH diteruskan
ke model sebagai prediksi yang diam-diam salah (CLAUDE.md: "Kegagalan API
harus memberi error terstruktur; jangan pernah menyamarkan kegagalan sebagai
prediksi valid").
"""

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from ..schema.raw_schema import RawDataSchema
from . import constants, registry


def _attach_lineage(result: pd.DataFrame, model_version: str) -> pd.DataFrame:
    """Tempelkan kolom lineage (``model_version``/``predicted_at``) ke hasil
    ``model.predict()`` -- dipakai bersama ``predict()`` dan
    ``predict_active()`` supaya logika shaping output tidak terduplikasi
    (satu sumber kebenaran)."""
    result = result.copy()
    result["model_version"] = str(model_version)
    result["predicted_at"] = datetime.now(timezone.utc).isoformat()
    return result


def predict(df: pd.DataFrame, model_version: str, tracking_uri: Optional[str] = None) -> pd.DataFrame:
    """Validasi ``df`` lewat ``RawDataSchema``, muat model versi ``model_version``
    dari MLflow registry, dan kembalikan DataFrame prediksi + lineage.

    Validasi WAJIB terjadi SEBELUM registry dipanggil (KK M1.5 -- data tidak
    valid tidak pernah sampai memuat model, dibuktikan lewat spy di
    ``tests/inference/test_predictor.py``).

    ``tracking_uri`` opsional -- default ``None`` diteruskan ke
    ``registry.load_model_by_version()`` yang lalu memakai
    ``constants.get_tracking_uri()`` (env var ``MLFLOW_TRACKING_URI``).
    """
    validated = RawDataSchema.validate(df)
    model = registry.load_model_by_version(model_version, tracking_uri=tracking_uri)
    result = model.predict(validated)
    return _attach_lineage(result, model_version)


def predict_active(
    df: pd.DataFrame,
    alias: str = constants.ACTIVE_ALIAS,
    tracking_uri: Optional[str] = None,
    model=None,
    resolved_version: Optional[str] = None,
) -> pd.DataFrame:
    """Validasi ``df``, muat model yang ditandai ``alias`` (default ``champion``
    -- "versi aktif", Milestone 2.1) dari MLflow registry, dan kembalikan
    DataFrame prediksi + lineage. Dipakai batch DAG (Milestone 2.5) dan
    real-time API (Milestone 3.2) -- TIDAK hardcode nomor versi, mengikuti
    alias kapan pun berpindah (promosi/rollback Milestone 2.8).

    Validasi WAJIB terjadi SEBELUM registry dipanggil, sama seperti
    ``predict()``.

    Kolom ``model_version`` di hasil berisi NOMOR VERSI KONKRET yang
    di-resolve dari alias saat pemanggilan ini (``registry.resolve_alias_version()``)
    -- BUKAN nama alias itu sendiri, karena alias mutable (bisa berpindah
    versi di masa depan) sementara lineage butuh menunjuk versi pasti yang
    benar-benar menghasilkan prediksi ini.

    ``model``/``resolved_version`` opsional -- kalau KEDUANYA diberikan, skip
    pemanggilan ``registry.load_active_model()``/``resolve_alias_version()``
    internal dan langsung pakai yang diberikan (Milestone 3.2: real-time API
    memuat model SEKALI saat startup dan meneruskannya di sini, supaya tidak
    fetch ulang artifact dari MLflow registry di SETIAP request HTTP). Default
    ``None`` mempertahankan perilaku lama (load fresh tiap panggilan) --
    dipakai apa adanya oleh batch DAG (Milestone 2.5), TIDAK ada perubahan
    perilaku untuk pemanggil existing.
    """
    validated = RawDataSchema.validate(df)
    if model is None or resolved_version is None:
        resolved_version = registry.resolve_alias_version(alias, tracking_uri=tracking_uri)
        model = registry.load_active_model(alias=alias, tracking_uri=tracking_uri)
    result = model.predict(validated)
    return _attach_lineage(result, resolved_version)
