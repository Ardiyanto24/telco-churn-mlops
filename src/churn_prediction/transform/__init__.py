"""Modul transformasi (preprocessing + feature engineering) untuk model churn
prediction telekomunikasi -- Milestone 1.2.

Sumber kebenaran: ``tccp-preprocessing-v2.ipynb`` cell 7-13 (DS), didokumentasikan
lengkap di ``docs/03-notebook-audit/notebook-audit.md``. Modul ini adalah port 1:1
logika tersebut, satu-satunya implementasi transformasi yang dipakai baik jalur
batch (Orang #2) maupun real-time API (Orang #3) -- prinsip "satu sumber
kebenaran" Bagian 2 dokumen arsitektur.

Kontrak:
    Input  : DataFrame 19 kolom fitur snake_case (skema ``telco_customers_synthetic``,
             ``docs/03-notebook-audit/notebook-audit.md`` Bagian H.3, minus target
             `churn` dan kolom metadata generator `synthetic_id`/`generation_id`/
             `generated_at` -- proyeksi kolom itu tanggung jawab pemanggil).
    Output : DataFrame 29 kolom numerik siap untuk model
             (``docs/03-notebook-audit/notebook-audit.md`` Bagian C).

Titik masuk utama: ``PreprocessingPipeline`` (lihat ``pipeline.py``), orkestrasi
6 step urutan KRITIS:
    FeatureEngineer -> ColumnDropper -> StructuralEncoder -> BinaryEncoder
    -> OHEWrapper -> ScalerWrapper

Sengaja TIDAK diport: ``DataSplitter`` (cell 14 notebook) -- split train/val/test
adalah kebutuhan training (di luar cakupan sistem ini), bukan kebutuhan jalur
serving yang dikonsumsi modul ini. Lihat
``milestones/1.2-modularisasi-preprocessing/decisions.md`` Keputusan #3.

Konvensi nama kolom snake_case (bukan PascalCase seperti notebook asli) adalah
keputusan eksplisit Milestone 1.2, lihat Keputusan #1 di file yang sama --
KT-1 (``docs/keputusan-tertunda.md``) yang menyebabkannya sudah ditutup dengan
keputusan ini, tapi kesepakatan formal Milestone 1.6 (jalur komunikasi perubahan
skema) masih menyusul terpisah.
"""
