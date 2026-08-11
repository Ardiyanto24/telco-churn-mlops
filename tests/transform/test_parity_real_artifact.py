"""Integration test -- KK2: bandingkan output modul kita terhadap
``preprocessor.joblib`` asli DS, dijalankan pada data real Supabase
(``telco_customers_source``).

Strategi (Keputusan #4, milestones/1.2-modularisasi-preprocessing/decisions.md):
1. Load ``preprocessor.joblib`` asli -- class-nya didefinisikan di kernel Kaggle
   (``__main__``), butuh shim ``sys.modules`` supaya bisa di-unpickle di sini.
2. "Graft" parameter fitted (StandardScaler.mean_/scale_, OneHotEncoder.categories_)
   dari objek asli ke instance ``PreprocessingPipeline`` kita -- skip fit(),
   langsung transform(). Valid karena parameter ini berbasis urutan POSISI
   kolom, bukan nama kolom.
3. Ambil baris nyata dari Supabase -- jalankan versi PascalCase asli lewat
   objek asli (ground truth), jalankan versi snake_case lewat modul kita.
4. Bandingkan nilai per fitur (dipetakan eksplisit, dua sisi punya nama kolom
   beda casing tapi harus menghasilkan angka identik).

Skip otomatis kalau ``SUPABASE_DB_URL`` tidak ada di ``.env``/environment atau
``artifacs/proprocessor/preprocessor.joblib`` tidak ditemukan.
"""

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "artifacs" / "proprocessor" / "preprocessor.joblib"
ENV_PATH = REPO_ROOT / ".env"


def _load_env_var(name):
    value = os.environ.get(name)
    if value:
        return value
    if not ENV_PATH.exists():
        return None
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return None


SUPABASE_DB_URL = _load_env_var("SUPABASE_DB_URL")

pytestmark = pytest.mark.skipif(
    not SUPABASE_DB_URL or not ARTIFACT_PATH.exists(),
    reason="butuh SUPABASE_DB_URL (.env) dan artifacs/proprocessor/preprocessor.joblib",
)

# Kolom mentah PascalCase (Supabase telco_customers_source) -> snake_case (modul kita).
RAW_PASCAL_TO_SNAKE = {
    "gender": "gender",
    "SeniorCitizen": "senior_citizen",
    "Partner": "partner",
    "Dependents": "dependents",
    "tenure": "tenure",
    "PhoneService": "phone_service",
    "MultipleLines": "multiple_lines",
    "InternetService": "internet_service",
    "OnlineSecurity": "online_security",
    "OnlineBackup": "online_backup",
    "DeviceProtection": "device_protection",
    "TechSupport": "tech_support",
    "StreamingTV": "streaming_tv",
    "StreamingMovies": "streaming_movies",
    "Contract": "contract",
    "PaperlessBilling": "paperless_billing",
    "PaymentMethod": "payment_method",
    "MonthlyCharges": "monthly_charges",
    "TotalCharges": "total_charges",
}

# Pemetaan eksplisit 29 kolom output ground-truth (PascalCase, dari preprocessor.joblib
# asli) -> 29 kolom output modul kita (snake_case). Statis & eksplisit -- lebih mudah
# diverifikasi manual daripada algoritma prefix-matching.
OUTPUT_COLUMN_MAP = {
    "SeniorCitizen": "senior_citizen",
    "Partner": "partner",
    "Dependents": "dependents",
    "tenure": "tenure",
    "PhoneService": "phone_service",
    "MultipleLines": "multiple_lines",
    "OnlineSecurity": "online_security",
    "OnlineBackup": "online_backup",
    "DeviceProtection": "device_protection",
    "TechSupport": "tech_support",
    "StreamingTV": "streaming_tv",
    "StreamingMovies": "streaming_movies",
    "PaperlessBilling": "paperless_billing",
    "MonthlyCharges": "monthly_charges",
    "tc_residual": "tc_residual",
    "monthly_to_total_ratio": "monthly_to_total_ratio",
    "is_auto_payment": "is_auto_payment",
    "service_count": "service_count",
    "has_any_addon": "has_any_addon",
    "Contract_One year": "contract_One year",
    "Contract_Two year": "contract_Two year",
    "InternetService_Fiber optic": "internet_service_Fiber optic",
    "InternetService_No": "internet_service_No",
    "PaymentMethod_Credit card (automatic)": "payment_method_Credit card (automatic)",
    "PaymentMethod_Electronic check": "payment_method_Electronic check",
    "PaymentMethod_Mailed check": "payment_method_Mailed check",
    "tenure_group_G2_2_18": "tenure_group_G2_2_18",
    "tenure_group_G3_18_44": "tenure_group_G3_18_44",
    "tenure_group_G4_44_72": "tenure_group_G4_44_72",
}


def _load_real_preprocessor():
    """Task 11: load preprocessor.joblib asli, tangani class-resolution.

    PENTING: shim mengarah ke class REFERENSI PascalCase (``_notebook_reference``),
    BUKAN class produksi kita (``churn_prediction.transform.*``). ``joblib.load()``
    hanya memulihkan atribut instance, bukan kode method -- kalau di-shim ke class
    produksi (snake_case), ``.transform()`` akan mengevaluasi kondisi kolom
    snake_case terhadap DataFrame PascalCase asli dan diam-diam gagal membuat
    beberapa fitur (mis. monthly_to_total_ratio, is_auto_payment) karena
    'total_charges' tidak pernah cocok dengan 'TotalCharges'. Ditemukan saat
    eksekusi milestone ini -- lihat logs.md.
    """
    import joblib

    import _notebook_reference as ref

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
        # (terlihat dari pesan warning-nya sendiri) -- temuan baru untuk KT-3.
        warnings.simplefilter("ignore")
        return joblib.load(ARTIFACT_PATH)


def _fetch_real_rows(limit=1500):
    import psycopg2

    conn = psycopg2.connect(SUPABASE_DB_URL, connect_timeout=15)
    cur = conn.cursor()
    cols_sql = ", ".join(f'"{c}"' if c[0].isupper() else c for c in ["id"] + list(RAW_PASCAL_TO_SNAKE.keys()))
    cur.execute(f"SELECT {cols_sql} FROM telco_customers_source ORDER BY id LIMIT %s;", (limit,))
    colnames = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=colnames)
    df["MonthlyCharges"] = df["MonthlyCharges"].astype(float)
    df["TotalCharges"] = df["TotalCharges"].astype(float)
    return df


def _graft_our_pipeline(real_obj):
    """Task 12: suntikkan parameter fitted dari objek asli ke instance kita.

    Deep-copy dulu supaya tidak memutasi objek ``real_obj`` yang juga dipakai
    sebagai ground truth. ``feature_names_in_`` dihapus dari salinan encoder/
    scaler kita -- sklearn modern memvalidasi nama kolom persis terhadap yang
    dilihat saat fit (PascalCase), padahal Keputusan #4 eksplisit: grafting
    ini seharusnya posisi-based, bukan nama-based.
    """
    import copy

    from churn_prediction.transform import constants
    from churn_prediction.transform.pipeline import PreprocessingPipeline

    mine = PreprocessingPipeline()

    mine.structural_encoder_.cols_present_ = list(constants.STRUCTURAL_COLS)
    mine.binary_encoder_.cols_present_ = list(constants.BINARY_COLS)
    mine.col_dropper_.cols_dropped_ = list(constants.DROP_COLS)

    mine.ohe_wrapper_.cols_present_ = list(constants.OHE_COLS) + ["tenure_group"]
    mine.ohe_wrapper_._encoder = copy.deepcopy(real_obj.ohe_wrapper_._encoder)
    if hasattr(mine.ohe_wrapper_._encoder, "feature_names_in_"):
        del mine.ohe_wrapper_._encoder.feature_names_in_
    # Tidak pakai encoder.get_feature_names_out(cols) -- encoder mengingat
    # feature_names_in_ dari fit asli (PascalCase) dan akan menolak nama snake_case
    # kita sebagai argumen (ValueError: input_features is not equal to
    # feature_names_in_). Bangun nama manual dari categories_/drop_idx_ (posisi-based,
    # sama-sama tidak bergantung nama kolom).
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


def test_kk2_parity_against_real_artifact_on_supabase_data():
    real_obj = _load_real_preprocessor()
    mine = _graft_our_pipeline(real_obj)

    df_pascal = _fetch_real_rows(limit=1500)
    assert set([0, 1, 2]).issubset(set(df_pascal["id"].tolist())), (
        "sampel harus mencakup baris id=0,1,2 (rujukan notebook-audit.md H.2)"
    )

    df_pascal_features = df_pascal.drop(columns=["id"])
    ground_truth = real_obj.transform(df_pascal_features)

    df_snake = df_pascal_features.rename(columns=RAW_PASCAL_TO_SNAKE)
    ours = mine.transform(df_snake)

    assert ours.shape == ground_truth.shape == (len(df_pascal), 29)
    assert set(OUTPUT_COLUMN_MAP.keys()) == set(ground_truth.columns)
    assert set(OUTPUT_COLUMN_MAP.values()) == set(ours.columns)

    mismatches = []
    for gt_col, our_col in OUTPUT_COLUMN_MAP.items():
        gt_vals = ground_truth[gt_col].to_numpy(dtype=float)
        our_vals = ours[our_col].to_numpy(dtype=float)
        if not np.allclose(gt_vals, our_vals, rtol=1e-6, atol=1e-8):
            n_diff = int((~np.isclose(gt_vals, our_vals, rtol=1e-6, atol=1e-8)).sum())
            mismatches.append(f"{gt_col!r} vs {our_col!r}: {n_diff}/{len(gt_vals)} baris beda")

    assert not mismatches, "Parity KK2 GAGAL:\n" + "\n".join(mismatches)
