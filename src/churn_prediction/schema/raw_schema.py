"""Skema/validasi data mentah PostgreSQL (jalur batch) -- pandera.

Dibangun terprogram dari `schema/constants.py` (Keputusan #2, satu sumber
constraint dipakai raw_schema dan request_schema) -- bukan menuliskan ulang
daftar kategori/rentang secara manual di sini.

Kontrak: DataFrame 19 kolom fitur snake_case (skema `telco_customers_synthetic`,
docs/03-notebook-audit/notebook-audit.md Bagian H.3 dikurangi target `churn`) --
identik kontrak input `churn_prediction.transform.PreprocessingPipeline`.
Memproyeksikan hanya kolom fitur (membuang `synthetic_id`/`generation_id`/
`generated_at`/`churn`) adalah tanggung jawab pemanggil sebelum validasi.

`strict=False` -- kolom di luar 19 kolom fitur (kalau pemanggil belum
memproyeksikan) tidak menyebabkan validasi gagal; skema ini fokus memvalidasi
KEHADIRAN dan KEBENARAN 19 kolom fitur, bukan melarang kolom tambahan.

Kolom numerik pakai `coerce=True` -- ditemukan saat Checkpoint 4 (uji
konsistensi terhadap request_schema.py/Pydantic): DataFrame satu-baris dengan
nilai `total_charges=0` (int) di-infer pandas sebagai `int64`, dan tanpa
`coerce`, pandera menolaknya murni karena dtype (int64 vs float64 dideklarasikan)
walau nilainya semantik valid -- sementara Pydantic otomatis coerce int->float.
`coerce=True` menyamakan perilaku (nilai int yang valid secara numerik tidak
ditolak hanya karena representasi tipe Python/pandas yang kebetulan berbeda).
Kolom kategorikal TETAP `coerce=False` (default) -- tidak ada alasan serupa
untuk melonggarkan tipe teks/kategori.
"""

import pandera.pandas as pa
from pandera.pandas import Check, Column

from . import constants

_columns: dict[str, Column] = {}

for _col, _categories in constants.CATEGORICAL_COLUMNS.items():
    _dtype = int if _col == "senior_citizen" else str
    _columns[_col] = Column(_dtype, Check.isin(_categories), nullable=False)

for _col, _spec in constants.NUMERIC_RANGES.items():
    _checks = []
    if "ge" in _spec:
        _checks.append(Check.ge(_spec["ge"]))
    if "le" in _spec:
        _checks.append(Check.le(_spec["le"]))
    if "gt" in _spec:
        _checks.append(Check.gt(_spec["gt"]))
    _columns[_col] = Column(_spec["dtype"], _checks, nullable=False, coerce=True)

RawDataSchema = pa.DataFrameSchema(_columns, strict=False, coerce=False)
"""pandera.DataFrameSchema untuk data mentah batch, 19 kolom fitur snake_case.

Penggunaan:
    from churn_prediction.schema.raw_schema import RawDataSchema
    validated_df = RawDataSchema.validate(df)  # raise pandera.errors.SchemaError kalau invalid
"""
