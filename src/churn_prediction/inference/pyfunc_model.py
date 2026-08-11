"""``ChurnPyfuncModel`` -- bundle tunggal preprocessor+model+threshold sebagai
satu custom ``mlflow.pyfunc.PythonModel`` -- Milestone 1.5.

Lihat milestones/1.5-inference-service/decisions.md Keputusan #5: satu artifact
per versi supaya rollback ke versi model lama otomatis memakai preprocessor
yang kompatibel dengannya, tanpa langkah sinkronisasi manual tambahan
(Bagian 5.4 dokumen arsitektur).

Bundle yang di-load lewat ``context.artifacts["bundle"]`` adalah hasil
``joblib.dump()`` dari dict ``{"pipeline": <PreprocessingPipeline ter-graft>,
"model": <VotingClassifier>, "threshold": <float>}`` -- dibangun oleh
``registry.build_bundle()``.
"""

import joblib
import mlflow.pyfunc
import pandas as pd

from .constants import POSITIVE_CLASS_INDEX


class ChurnPyfuncModel(mlflow.pyfunc.PythonModel):
    """Pyfunc model: ``transform()`` (preprocessing) -> ``predict_proba()`` (model)
    -> threshold -> DataFrame ``churn_probability``+``churn_label``.

    Threshold disimpan DI DALAM bundle (bukan konstanta global) -- versi
    berbeda bisa punya threshold berbeda, itu yang dipakai KK3 (Milestone 1.5
    Checkpoint 3) untuk membuktikan mekanisme load-by-version version-aware.
    """

    def load_context(self, context):
        bundle = joblib.load(context.artifacts["bundle"])
        self._pipeline = bundle["pipeline"]
        self._model = bundle["model"]
        self._threshold = bundle["threshold"]

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        transformed = self._pipeline.transform(model_input)
        probabilities = self._model.predict_proba(transformed)[:, POSITIVE_CLASS_INDEX]
        labels = (probabilities >= self._threshold).astype(int)
        return pd.DataFrame(
            {"churn_probability": probabilities, "churn_label": labels},
            index=model_input.index,
        )
