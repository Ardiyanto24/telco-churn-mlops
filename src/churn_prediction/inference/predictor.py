"""API publik ``predict(df, model_version) -> DataFrame`` -- titik masuk utama
package ``churn_prediction.inference``, Milestone 1.5.

Kontrak (milestones/1.5-inference-service/decisions.md Keputusan #3/#4):
    Input  : ``pandas.DataFrame`` (1+ baris), skema sama dengan
             ``churn_prediction.schema.raw_schema.RawDataSchema`` (19 kolom
             fitur snake_case). Validasi dijalankan DI DALAM fungsi ini --
             bukan diasumsikan sudah dilakukan pemanggil.
    Output : ``pandas.DataFrame`` (urutan baris = urutan input), kolom:
             ``churn_probability`` (float), ``churn_label`` (int 0/1, dari
             threshold yang tersimpan di bundle versi yang dimuat),
             ``model_version`` (str), ``predicted_at`` (ISO8601 UTC).

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
from . import registry


def predict(df: pd.DataFrame, model_version: str, tracking_uri: Optional[str] = None) -> pd.DataFrame:
    """Validasi ``df`` lewat ``RawDataSchema``, muat model versi ``model_version``
    dari MLflow registry, dan kembalikan DataFrame prediksi + lineage.

    ``tracking_uri`` opsional -- default ``None`` diteruskan ke
    ``registry.load_model_by_version()`` yang lalu memakai
    ``constants.get_tracking_uri()`` (env var ``MLFLOW_TRACKING_URI``).
    """
    validated = RawDataSchema.validate(df)

    model = registry.load_model_by_version(model_version, tracking_uri=tracking_uri)
    result = model.predict(validated)

    result = result.copy()
    result["model_version"] = str(model_version)
    result["predicted_at"] = datetime.now(timezone.utc).isoformat()
    return result
