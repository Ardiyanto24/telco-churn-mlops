"""Pemetaan nama kolom `telco_customers_source` (PascalCase) ke konvensi
snake_case yang dipakai `churn_prediction.transform`/`schema.raw_schema`
(mengikuti `telco_customers_synthetic`, keputusan M1.2) -- Milestone 2.5.

Sebelumnya terduplikasi di 3 file test (`tests/inference/test_e2e_parity.py`,
`tests/transform/test_parity_real_artifact.py`,
`tests/schema/test_raw_schema_supabase.py`) -- disentralisasi di sini supaya
titik baca data (batch DAG, real-time API M3.x, test) punya SATU sumber
kebenaran pemetaan, bukan didefinisikan ulang tiap tempat (risiko drift diam-
diam antar salinan). Lihat `milestones/1.6-kontrak-skema-sumber-data/
decisions.md` Keputusan #1 (titik baca data WAJIB me-rename eksplisit
sebelum memanggil modul transform -- modul transform sendiri tidak berubah).
"""

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
