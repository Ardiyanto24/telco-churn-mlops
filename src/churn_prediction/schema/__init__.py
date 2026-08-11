"""Skema dan validasi data input -- Milestone 1.3.

Dua kontrak terpisah (Bagian 3.5 dokumen arsitektur), dibangun dari satu
sumber constraint (`schema/constants.py`, Keputusan #2):

- `raw_schema.RawDataSchema` (pandera) -- validasi data mentah batch dari
  PostgreSQL (`telco_customers_synthetic`).
- `request_schema.ChurnPredictionRequest` (Pydantic) -- validasi request
  real-time API.

Konvensi field request real-time SENGAJA snake_case identik nama kolom
(Keputusan #4) -- pemetaan field-ke-kolom di bawah ini karena itu adalah
IDENTITY MAPPING, tapi tetap didokumentasikan penuh (bukan diasumsikan
trivial dan dilewatkan) sesuai KK2 milestone ini: pemetaan field-ke-kolom
harus terdokumentasi jelas, walau field dan kolom kebetulan sama namanya.

## Pemetaan Field Request -> Kolom Data Mentah

| Field request (Pydantic) | Kolom data mentah (pandera) | Tipe | Constraint |
|---|---|---|---|
| `gender` | `gender` | str | {Female, Male} |
| `senior_citizen` | `senior_citizen` | int | {0, 1} |
| `partner` | `partner` | str | {Yes, No} |
| `dependents` | `dependents` | str | {Yes, No} |
| `tenure` | `tenure` | int | 1 <= x <= 72 |
| `phone_service` | `phone_service` | str | {Yes, No} |
| `multiple_lines` | `multiple_lines` | str | {Yes, No, No phone service} |
| `internet_service` | `internet_service` | str | {DSL, Fiber optic, No} |
| `online_security` | `online_security` | str | {Yes, No, No internet service} |
| `online_backup` | `online_backup` | str | {Yes, No, No internet service} |
| `device_protection` | `device_protection` | str | {Yes, No, No internet service} |
| `tech_support` | `tech_support` | str | {Yes, No, No internet service} |
| `streaming_tv` | `streaming_tv` | str | {Yes, No, No internet service} |
| `streaming_movies` | `streaming_movies` | str | {Yes, No, No internet service} |
| `contract` | `contract` | str | {Month-to-month, One year, Two year} |
| `paperless_billing` | `paperless_billing` | str | {Yes, No} |
| `payment_method` | `payment_method` | str | {Bank transfer (automatic), Credit card (automatic), Electronic check, Mailed check} |
| `monthly_charges` | `monthly_charges` | float | x > 0 |
| `total_charges` | `total_charges` | float | x >= 0 |

19 baris -- identik `schema.constants.FEATURE_COLUMNS`, diverifikasi terprogram
di `tests/schema/test_schema_consistency.py::test_field_sets_identical`.

Field/kolom TIDAK termasuk di sini (sengaja, lihat `decisions.md` Keputusan #4):
`id`/`synthetic_id`/`generation_id`/`generated_at` (metadata generator/database,
bukan fitur model) dan `churn` (target, bukan input).
"""
