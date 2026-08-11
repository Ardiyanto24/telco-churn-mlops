# Kontrak Skema Data Mentah — Sumber PostgreSQL/Supabase

**Status:** Disepakati — Milestone 1.6 (`milestones/1.6-kontrak-skema-sumber-data/decisions.md`), versi kontrak v1 (2026-08-12).

**Tujuan dokumen:** rujukan tunggal skema tabel sumber PostgreSQL yang jadi input model churn — kolom, tipe, semantik ambigu (unit, null, timezone), dan kontrak jalur baca untuk Milestone 1.1-1.3 (Orang #1) serta Milestone 2.x/3.x (Orang #2/#3). Diverifikasi cocok dengan struktur tabel sungguhan di Supabase per 2026-08-12 (`milestones/1.6-kontrak-skema-sumber-data/logs.md` Checkpoint 1) — bukan disalin dari dokumen lama tanpa verifikasi ulang.

---

## 1. Kontrak Dua-Fase — Tabel Mana yang Dibaca Kapan

Ada DUA tabel yang merepresentasikan pelanggan secara semantik sama (21 atribut bisnis), tapi berbeda konvensi nama kolom dan status operasional. Sistem ini memakainya secara BERTAHAP, bukan memilih satu selamanya:

| Fase | Tabel dibaca | Kapan berlaku |
|---|---|---|
| **Fase 1 — Sekarang (pengembangan M2.x/M3.x)** | `telco_customers_source` (PascalCase, 594.194 baris statis nyata) | Sampai seluruh sistem MLOps ini selesai dibangun |
| **Fase 2 — Produksi resmi** | `telco_customers_synthetic` (snake_case, near-real-time) | Begitu seluruh sistem selesai DAN data generator diaktifkan (trigger, bukan tanggal pasti) |

Begitu Fase 2 berlaku, `telco_customers_source` **deprecated untuk jalur production** — tetap ada sebagai referensi data training historis (byte-identik dataset Kaggle asli, `notebook-audit.md` Bagian H.2), tidak pernah dihapus.

**Konsekuensi untuk pemanggil (WAJIB dipatuhi M2.x/M3.x):**
- Modul `churn_prediction.transform`/`churn_prediction.schema`/`churn_prediction.inference` **TIDAK berubah** — tetap menerima DataFrame snake_case (keputusan M1.2, tidak direvisi kontrak ini).
- Selama Fase 1 (baca `telco_customers_source`), titik baca data (mis. batch DAG Milestone 2.5) **WAJIB me-rename PascalCase→snake_case eksplisit** sebelum memanggil modul `transform`/`inference` — pola sama persis dengan `RAW_PASCAL_TO_SNAKE` yang sudah dipakai `tests/transform/test_parity_real_artifact.py` dan `tests/inference/test_e2e_parity.py`. JANGAN menulis ulang logika transformasi untuk menerima PascalCase langsung.
- Saat Fase 2 dimulai, rename ini tidak dibutuhkan lagi (nama kolom sudah cocok native) — titik baca data cukup diarahkan ulang ke `telco_customers_synthetic`.

(Ini menutup KT-1, `docs/keputusan-tertunda.md`.)

---

## 2. Skema Kolom Lengkap

### 2.1 `telco_customers_source` (Fase 1 — sumber aktif sekarang)

Primary key: `id` (bigint, NOT NULL). 594.194 baris, dimuat SEKALI dari Kaggle Playground Series S6E3 (`imported_at` identik di semua baris — bukti bulk-load satu kali, bukan streaming).

| Kolom | Tipe PostgreSQL | Nullable | Kategori/Rentang Valid | Catatan |
|---|---|---|---|---|
| `id` | bigint | NOT NULL | 0–594.193, unik | Primary key |
| `gender` | text | nullable* | Female, Male | *nullable di skema, 0 NULL aktual (verifikasi M1.1) |
| `SeniorCitizen` | smallint | nullable* | 0, 1 | |
| `Partner` | text | nullable* | Yes, No | |
| `Dependents` | text | nullable* | Yes, No | |
| `tenure` | integer | nullable* | 1–72 | **Satuan: bulan** (lihat Bagian 3.2) |
| `PhoneService` | text | nullable* | Yes, No | |
| `MultipleLines` | text | nullable* | Yes, No, No phone service | |
| `InternetService` | text | nullable* | DSL, Fiber optic, No | |
| `OnlineSecurity` | text | nullable* | Yes, No, No internet service | |
| `OnlineBackup` | text | nullable* | Yes, No, No internet service | |
| `DeviceProtection` | text | nullable* | Yes, No, No internet service | |
| `TechSupport` | text | nullable* | Yes, No, No internet service | |
| `StreamingTV` | text | nullable* | Yes, No, No internet service | |
| `StreamingMovies` | text | nullable* | Yes, No, No internet service | |
| `Contract` | text | nullable* | Month-to-month, One year, Two year | |
| `PaperlessBilling` | text | nullable* | Yes, No | |
| `PaymentMethod` | text | nullable* | Bank transfer (automatic), Credit card (automatic), Electronic check, Mailed check | |
| `MonthlyCharges` | numeric | nullable* | > 0 | **Satuan: USD** (lihat Bagian 3.1) |
| `TotalCharges` | numeric | nullable* | >= 0 | **Satuan: USD** |
| `Churn` | text | nullable* | Yes, No | Target model |
| `imported_at` | timestamptz | NOT NULL, default `now()` | — | Metadata audit-load, BUKAN kolom bisnis/fitur. Nilai identik di semua baris (bulk load 2026-08-08 06:56:20 UTC) |

### 2.2 `telco_customers_synthetic` (Fase 2 — kontrak produksi resmi setelah generator aktif)

Primary key: `synthetic_id` (uuid, NOT NULL). Foreign key: `generation_id` → `synthetic_generation_runs.generation_id`. **0 baris saat ini** (generator belum pernah diaktifkan). Seluruh 20 kolom bisnis `NOT NULL` (lebih ketat dari `telco_customers_source`).

| Kolom | Tipe PostgreSQL | Nullable | Kategori/Rentang Valid (CHECK constraint) |
|---|---|---|---|
| `synthetic_id` | uuid | NOT NULL | Primary key |
| `generation_id` | uuid | NOT NULL | FK → `synthetic_generation_runs.generation_id` |
| `generated_at` | timestamptz | NOT NULL | Timestamp generate baris ini |
| `gender` | text | NOT NULL | Female, Male |
| `senior_citizen` | smallint | NOT NULL | CHECK `IN (0,1)` |
| `partner` | text | NOT NULL | Yes, No |
| `dependents` | text | NOT NULL | Yes, No |
| `tenure` | integer | NOT NULL | CHECK `1 <= tenure <= 72` (bulan) |
| `phone_service` | text | NOT NULL | Yes, No |
| `multiple_lines` | text | NOT NULL | Yes, No, No phone service |
| `internet_service` | text | NOT NULL | DSL, Fiber optic, No |
| `online_security` | text | NOT NULL | Yes, No, No internet service |
| `online_backup` | text | NOT NULL | Yes, No, No internet service |
| `device_protection` | text | NOT NULL | Yes, No, No internet service |
| `tech_support` | text | NOT NULL | Yes, No, No internet service |
| `streaming_tv` | text | NOT NULL | Yes, No, No internet service |
| `streaming_movies` | text | NOT NULL | Yes, No, No internet service |
| `contract` | text | NOT NULL | Month-to-month, One year, Two year |
| `paperless_billing` | text | NOT NULL | Yes, No |
| `payment_method` | text | NOT NULL | Bank transfer (automatic), Credit card (automatic), Electronic check, Mailed check |
| `monthly_charges` | numeric | NOT NULL | CHECK `> 0` (USD) |
| `total_charges` | numeric | NOT NULL | CHECK `>= 0` (USD) |
| `churn` | text | NOT NULL | CHECK `IN ('Yes','No')` |

**GAP TERBUKA (lihat Bagian 4 dan KT-4, `docs/keputusan-tertunda.md`):** tabel ini TIDAK punya kolom identitas pelanggan yang stabil lintas baris (`synthetic_id` unik PER BARIS, bukan per pelanggan). Wajib ditambahkan sebelum generator diaktifkan — lihat Bagian 4.

### 2.3 `synthetic_generation_runs` (metadata tiap batch generasi — 0 baris, belum pernah jalan)

| Kolom | Tipe PostgreSQL | Nullable | Kategori/Rentang Valid |
|---|---|---|---|
| `generation_id` | uuid | NOT NULL | Primary key |
| `requested_count` | integer | NOT NULL | CHECK `1 <= x <= 100000` |
| `inserted_count` | integer | NOT NULL, default 0 | — |
| `seed` | bigint | nullable | Untuk reproducibility generasi |
| `status` | text | NOT NULL | CHECK `IN ('completed','failed')` — TIDAK ada state `'pending'`/`'running'`, berarti baris hanya ditulis SETELAH proses selesai/gagal |
| `created_at` | timestamptz | NOT NULL, default `now()` | |
| `completed_at` | timestamptz | nullable | |

---

## 3. Semantik Ambigu — Didokumentasikan Eksplisit

### 3.1 Satuan angka

- `monthly_charges`/`total_charges`/`MonthlyCharges`/`TotalCharges`: **USD** — dataset Telco Customer Churn (IBM, via Kaggle Playground Series S6E3) memakai dolar AS sebagai satuan standar publikasinya.
- `tenure`: **bulan** — dikonfirmasi oleh CHECK constraint (`1 <= tenure <= 72`, konsisten rentang 1-72 bulan/6 tahun pelanggan telekomunikasi) dan `TENURE_BINS`/label (`churn_prediction.transform.constants`, sudah memakai satuan bulan sejak Milestone 1.2).

### 3.2 Timezone

Seluruh kolom timestamp (`imported_at`, `generated_at`, `created_at`, `completed_at`) bertipe PostgreSQL `timestamptz` — **otomatis ternormalisasi UTC secara internal** oleh PostgreSQL (bukan ambiguitas yang perlu diputuskan; konsekuensi langsung dari tipe kolom itu sendiri). Pemanggil yang membaca kolom ini lewat driver Python (`psycopg2`) akan menerima objek `datetime` timezone-aware (UTC), bukan naive.

### 3.3 Null handling

- `telco_customers_source`: 21 kolom bisnis nullable di level skema, TAPI **0 NULL aktual** di 594.194 baris (diverifikasi M1.1 dan M1.6 Checkpoint 1) — dalam praktiknya berperilaku sama seperti NOT NULL.
- `telco_customers_synthetic`: seluruh 20 kolom bisnis **NOT NULL di-enforce skema** (lebih ketat) — generator TIDAK BOLEH menulis nilai kosong untuk kolom bisnis apa pun.
- Konsekuensi untuk modul `churn_prediction.schema`: `raw_schema.py`/`request_schema.py` (Milestone 1.3) sudah mendefinisikan seluruh 19 kolom fitur sebagai `nullable=False` — konsisten dengan kontrak ini di kedua tabel.

---

## 4. Semantik Update: Append-Only Snapshot (Menutup KT-2)

**Kontrak yang disepakati untuk desain generator ke depan** (implementasi generator itu sendiri di luar cakupan sistem ini — "given", lihat `mlops-01-productionization.md`):

- Setiap kejadian generator menghasilkan **baris BARU** (`synthetic_id` baru) — baris yang sudah ada TIDAK PERNAH di-update in-place.
- "Current state" per pelanggan didefinisikan sebagai **baris TERBARU** per identitas pelanggan, mis.:
  ```sql
  SELECT DISTINCT ON (customer_key) *
  FROM telco_customers_synthetic
  ORDER BY customer_key, generated_at DESC;
  ```
- Pola ini (dikenal *Slowly Changing Dimension Type 2* di data warehousing) dipilih karena: (a) tidak pernah menghapus informasi — auditable, bisa "replay" kondisi data di titik waktu tertentu; (b) otomatis menyediakan bahan fitur historis/agregat untuk kebutuhan feature store (Milestone 2.2/2.3) tanpa perlu tabel log terpisah; (c) TIDAK berdampak ke model yang sudah dilatih sekarang — seluruh 29 fitur final (`notebook-audit.md` Bagian C) berstatus **INSTANT** (dihitung dari satu baris, bukan agregasi historis), jadi keputusan ini murni desain sistem ke depan.

**GAP KONKRET (dicatat sebagai KT-4, `docs/keputusan-tertunda.md`):** skema `telco_customers_synthetic` SAAT INI (Bagian 2.2 di atas, diverifikasi ulang M1.6 Checkpoint 1) **tidak punya kolom `customer_key`** (atau setara) yang stabil lintas baris untuk merepresentasikan "pelanggan yang sama". `synthetic_id` adalah identitas PER BARIS/PER KEJADIAN, bukan per pelanggan. Query "current state" di atas TIDAK BISA dijalankan sampai kolom ini ditambahkan. Ini WAJIB diselesaikan (migrasi skema, koordinasi dengan pemilik sistem generator) sebelum generator pertama kali diaktifkan — bukan pekerjaan Milestone 1.6.

---

## 5. Jalur Komunikasi Perubahan Skema

Lihat `docs/04-schema-contract/CHANGELOG.md` — **WAJIB dibaca sebelum memulai pekerjaan apa pun yang bergantung pada kontrak ini** (Milestone 2.x/3.x, dan kunjungan ulang ke Milestone 1.1-1.3 kalau skema berubah).
