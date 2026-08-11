"""Test integrasi -- membuktikan gerbang skema->transform bekerja sebagai satu
rangkaian (audit Milestone 1.4 Checkpoint 1, Temuan 4).

M1.2 (`churn_prediction.transform`) dan M1.3 (`churn_prediction.schema`) diuji
seluruhnya terpisah selama ini -- tidak ada test yang membuktikan data yang
DITOLAK `RawDataSchema` benar-benar tidak pernah sampai diproses
`PreprocessingPipeline`, atau bahwa data yang LOLOS `RawDataSchema` bisa
diproses `PreprocessingPipeline` tanpa error tak terduga. Pola ini yang akan
dipakai batch (M2.5)/real-time (M3.2) nanti: validasi dulu, baru transform.
"""

from unittest.mock import patch

import pandas as pd
import pandera.errors
import pytest

from churn_prediction.schema.raw_schema import RawDataSchema
from churn_prediction.transform.pipeline import PreprocessingPipeline


def _valid_row(**overrides):
    row = {
        "gender": "Male",
        "senior_citizen": 0,
        "partner": "Yes",
        "dependents": "No",
        "tenure": 29,
        "phone_service": "Yes",
        "multiple_lines": "No",
        "internet_service": "DSL",
        "online_security": "Yes",
        "online_backup": "No",
        "device_protection": "Yes",
        "tech_support": "Yes",
        "streaming_tv": "No",
        "streaming_movies": "No",
        "contract": "One year",
        "paperless_billing": "Yes",
        "payment_method": "Mailed check",
        "monthly_charges": 60.10,
        "total_charges": 1653.85,
    }
    row.update(overrides)
    return row


def test_valid_data_passes_schema_then_transform_successfully():
    # PENTING: fit_transform() butuh baris yang mencakup SEMUA kategori tiap kolom
    # OHE -- ditemukan saat menulis test ini (bukan bug pipeline). Percobaan pertama
    # (1 baris) -> OneHotEncoder(drop='first') hanya lihat 1 kategori/kolom, drop='first'
    # menghapus satu-satunya kategori itu -> 0 dummy, output 19 kolom (bukan 29).
    # Percobaan kedua (3 baris, kategori tidak lengkap) -> 27 kolom (2 kategori
    # tenure_group/payment_method belum pernah muncul, tidak menghasilkan dummy).
    # Baru dengan seluruh kategori (4 baris, konsisten fixture test_pipeline.py)
    # hasilnya 29 kolom penuh. Ini karakteristik sklearn yang benar (konsisten
    # prinsip "fit hanya di training data yang representatif"), bukan sesuatu
    # yang perlu diperbaiki -- dicatat supaya tidak terulang jadi kebingungan.
    df = pd.DataFrame(
        [
            _valid_row(contract="Month-to-month", internet_service="DSL", payment_method="Bank transfer (automatic)", tenure=1),
            _valid_row(contract="One year", internet_service="Fiber optic", payment_method="Credit card (automatic)", tenure=10),
            _valid_row(contract="Two year", internet_service="No", payment_method="Electronic check", tenure=30),
            _valid_row(contract="One year", internet_service="DSL", payment_method="Mailed check", tenure=60),
        ]
    )

    validated = RawDataSchema.validate(df)
    out = PreprocessingPipeline().fit_transform(validated)

    assert out.shape == (4, 29)
    assert not out.isnull().any().any()


def test_invalid_data_rejected_before_reaching_transform():
    """Data yang ditolak RawDataSchema TIDAK PERNAH sampai ke PreprocessingPipeline
    -- dibuktikan dengan spy pada fit_transform, bukan cuma diasumsikan dari
    urutan baris kode."""
    df = pd.DataFrame([_valid_row(tenure=200)])  # di luar rentang [1,72]

    with patch.object(
        PreprocessingPipeline, "fit_transform", wraps=PreprocessingPipeline.fit_transform
    ) as spy_fit_transform:
        with pytest.raises(pandera.errors.SchemaError, match="tenure"):
            validated = RawDataSchema.validate(df)
            PreprocessingPipeline().fit_transform(validated)

        spy_fit_transform.assert_not_called()


@pytest.mark.parametrize(
    "override",
    [
        {"tenure": 0},
        {"monthly_charges": -5.0},
        {"senior_citizen": 2},
        {"contract": "Weekly"},
    ],
)
def test_multiple_invalid_cases_all_blocked_before_transform(override):
    df = pd.DataFrame([_valid_row(**override)])

    with patch.object(
        PreprocessingPipeline, "fit_transform", wraps=PreprocessingPipeline.fit_transform
    ) as spy_fit_transform:
        with pytest.raises(pandera.errors.SchemaError):
            validated = RawDataSchema.validate(df)
            PreprocessingPipeline().fit_transform(validated)

        spy_fit_transform.assert_not_called()
