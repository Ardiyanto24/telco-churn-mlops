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

from ..schema.column_mapping import RAW_PASCAL_TO_SNAKE
from .constants import POSITIVE_CLASS_INDEX

# Preprocessor+model asli DS di-fit TANPA nama fitur (numpy array polos --
# dikonfirmasi via UserWarning sklearn "fitted without feature names" saat
# transform dipanggil) -- artinya POSISI kolom, bukan cuma nama, menentukan
# hasil `pipeline.transform()`/`model.predict_proba()` di internal
# sklearn/lightgbm/xgboost. `RAW_PASCAL_TO_SNAKE.values()` adalah urutan
# kanonik (mengikuti kolom dataset asli/`telco_customers_synthetic`, lihat
# `schema/column_mapping.py`) -- SATU-SATUNYA urutan yang terbukti cocok
# dengan preprocessor asli (dibuktikan lewat KK2 Milestone 1.5, ground truth
# raw artifact). Ditemukan Milestone 3.2: DataFrame dari
# `ChurnPredictionRequest.model_dump()` (urutan field beda -- kolom numerik
# di akhir) menghasilkan `churn_probability` BERBEDA (bukan floating-point
# noise, delta hingga ~0.36) padahal NAMA+NILAI kolom identik -- silent
# wrong prediction, bukan error. Lihat
# milestones/3.2-real-time-inference-api/decisions.md.
_CANONICAL_COLUMN_ORDER = list(RAW_PASCAL_TO_SNAKE.values())


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
        # Reorder ke urutan kanonik SEBELUM masuk pipeline -- lihat komentar
        # `_CANONICAL_COLUMN_ORDER` di atas. Caller manapun (nama kolom benar,
        # urutan apa pun) menghasilkan prediksi BENAR dan KONSISTEN, bukan
        # bergantung urutan DataFrame yang kebetulan dikirim.
        model_input = model_input[_CANONICAL_COLUMN_ORDER]
        transformed = self._pipeline.transform(model_input)
        probabilities = self._model.predict_proba(transformed)[:, POSITIVE_CLASS_INDEX]
        labels = (probabilities >= self._threshold).astype(int)
        return pd.DataFrame(
            {"churn_probability": probabilities, "churn_label": labels},
            index=model_input.index,
        )
