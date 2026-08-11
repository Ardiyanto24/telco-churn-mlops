# Decisions — Milestone 1.6: Kontrak Skema dengan Sumber Data

## Klarifikasi Sebelum Plan Disusun

Tiga pertanyaan diajukan ke user sebelum plan ditulis, dengan diskusi lanjutan untuk 2 di antaranya:

1. **KT-1 (tabel mana jadi kontrak resmi):** dijawab dengan skenario DUA FASE — `telco_customers_source` dipakai SEKARANG untuk pengembangan/testing, lalu switch ke `telco_customers_synthetic` begitu generator diaktifkan. User konfirmasi generator akan diaktifkan **setelah seluruh sistem MLOps ini selesai dibangun**.
2. **KT-2 (update in-place vs snapshot):** user tidak tahu jawaban pasti, minta rekomendasi standar industri. Direkomendasikan **append-only snapshot (SCD Type 2)** — dikonfirmasi ulang tidak berdampak ke model yang sudah dilatih (seluruh 29 fitur final berstatus INSTANT). Ditemukan gap: skema `telco_customers_synthetic` tidak punya kolom identitas pelanggan stabil terpisah dari `synthetic_id`. User setuju rekomendasi, gap dicatat sebagai follow-up.
3. **Jalur komunikasi perubahan skema:** user ingin proyek solo ini sedekat mungkin standar kerja tim sungguhan. Direkomendasikan pola "data contract" versioned dengan CHANGELOG eksplisit. User setuju.

## Keputusan Teknis

### 1. Kontrak tabel dua-fase: `telco_customers_source` sekarang, `telco_customers_synthetic` resmi setelah generator aktif — menutup KT-1

**Keputusan:** `telco_customers_source` tetap jadi sumber data yang benar-benar dibaca selama pengembangan (M2.x/M3.x, sampai sistem selesai). Begitu seluruh sistem MLOps ini selesai dibangun DAN data generator diaktifkan (trigger eksplisit, bukan tanggal pasti), `telco_customers_synthetic` menjadi kontrak resmi produksi — `telco_customers_source` deprecated untuk jalur production (tetap ada sebagai referensi data training historis). Modul `churn_prediction.transform` TIDAK berubah (tetap snake_case, keputusan M1.2 tidak direvisi) — selama fase `source` dipakai, titik baca data (batch DAG M2.5, dsb) WAJIB me-rename PascalCase→snake_case eksplisit sebelum memanggil modul transform (pola sama `RAW_PASCAL_TO_SNAKE` yang sudah dipakai `test_parity_real_artifact.py`/`test_e2e_parity.py`), bukan modul transform yang diubah menerima dua konvensi.

**Kenapa:** Dikonfirmasi user langsung — jawaban lebih presisi dari 3 opsi awal yang ditawarkan (dua fase dengan trigger jelas, bukan pilih satu selamanya). Konsisten dengan arah M1.2 (snake_case mengikuti `telco_customers_synthetic`) sebagai tujuan akhir, sekaligus realistis dengan kondisi sekarang (generator belum aktif, `synthetic` masih 0 baris — memaksa pakai `synthetic` sekarang berarti sistem tidak pernah punya data untuk didemo).

### 2. Semantik update generator: append-only snapshot (SCD Type 2) — menutup KT-2, dengan follow-up gap skema

**Keputusan:** Desain generator ke depan (di luar cakupan implementasi sistem ini, tapi disepakati sebagai kontrak semantik yang diasumsikan modul-modul hilir) memakai pola **append-only snapshot**: tiap kejadian generator menghasilkan baris BARU (`synthetic_id` baru), baris lama tidak pernah diubah. "Current state" per pelanggan = baris TERBARU per identitas pelanggan. Gap konkret ditemukan dan dicatat sebagai KT-4 baru (`docs/keputusan-tertunda.md`): skema `telco_customers_synthetic` saat ini TIDAK punya kolom identitas pelanggan stabil terpisah dari `synthetic_id` — perlu kolom baru (mis. `customer_key`) sebelum generator bisa mengimplementasikan pola ini dengan benar. Ini murni temuan+dokumentasi, BUKAN migrasi skema yang dikerjakan di M1.6.

**Kenapa:** Direkomendasikan sebagai standar industri (SCD Type 2 adalah pola textbook data warehousing untuk skenario "profil entitas berubah dari waktu ke waktu"). Dikonfirmasi TIDAK berdampak ke model yang sudah dilatih (re-verifikasi eksplisit: seluruh 29 fitur final `notebook-audit.md` Bagian C berstatus INSTANT, tidak ada HISTORICAL/agregat — keputusan ini murni forward-looking system design). Tidak menghapus informasi (auditable, bisa "replay" kondisi data di titik waktu tertentu) dan otomatis menyediakan bahan fitur historis/agregat untuk retraining masa depan tanpa perlu tabel log terpisah — persis kebutuhan yang sudah diantisipasi arsitektur (feature store M2.2/M2.3). User setuju eksplisit setelah rekomendasi dijelaskan.

### 3. Jalur komunikasi: data contract versioned dengan CHANGELOG eksplisit

**Keputusan:** Dokumen kontrak skema (`docs/04-schema-contract/raw-schema-contract.md`) disertai `docs/04-schema-contract/CHANGELOG.md` terpisah — format entry (tanggal, apa yang berubah, breaking/non-breaking, milestone yang terdampak), aturan eksplisit apa yang dianggap breaking (kolom dihapus/rename/ganti tipe/constraint diperketat) vs non-breaking (kolom baru nullable/dengan default). Perubahan skema ke depan WAJIB lewat git PR (approve sendiri tetap OK untuk solo project, tapi riwayat PR jadi jejak "review" formal) yang menyentuh dokumen ini. Milestone yang bergantung pada kontrak ini (M2.x/M3.x) WAJIB membaca CHANGELOG sebelum mulai.

**Kenapa:** Direkomendasikan sebagai pola "data contract" standar industri (dipakai platform data/ML production sungguhan) — meniru disiplin kerja tim nyata meski dikerjakan solo, sesuai permintaan eksplisit user. User setuju eksplisit setelah rekomendasi dijelaskan.

### 4. Semantik unit/timezone/null: didokumentasikan penuh dari bukti yang sudah ada, tidak perlu tanya ulang ke user

**Keputusan:** Kontrak skema mendokumentasikan eksplisit: `monthly_charges`/`total_charges` dalam USD (dataset Kaggle publik dikenal luas — Telco Customer Churn dataset IBM), `tenure` dalam bulan (dikonfirmasi CHECK constraint `1<=tenure<=72` + `TENURE_BINS`/label sudah memakai satuan bulan sejak M1.2), kolom timestamp (`imported_at`, `generated_at`, `created_at`, `completed_at`) bertipe `timestamptz` PostgreSQL (otomatis ternormalisasi UTC secara internal), null handling (`telco_customers_source`: nullable tapi 0 NULL aktual di 594.194 baris; `telco_customers_synthetic`: `NOT NULL` di-enforce skema, lebih ketat).

**Kenapa:** Bukan keputusan baru yang perlu ditanyakan — bukti sudah kuat dan konklusif dari audit M1.1 (Bagian A, H.3) dan definisi tipe PostgreSQL sendiri. Tetap didokumentasikan PENUH di kontrak (bukan diasumsikan trivial dan dilewatkan) — konsisten prinsip KK2 M1.3 (pemetaan/semantik didokumentasikan eksplisit walau kelihatan "sudah jelas").

### 5. Dokumen kontrak substantif di `docs/`, bukan `milestones/`

**Keputusan:** `docs/04-schema-contract/raw-schema-contract.md` + `docs/04-schema-contract/CHANGELOG.md` (nomor urut `04-` mengikuti `01-architecture`/`02-implementation-plan`/`03-notebook-audit` yang sudah ada). `milestones/1.6-kontrak-skema-sumber-data/` HANYA berisi `decisions.md`/`logs.md`/`report.md`.

**Kenapa:** Konsisten koreksi user di M1.1 — dokumen substantif yang akan dirujuk terus-menerus oleh milestone lain (di sini: M1.1-1.3 dan terutama M2.x/M3.x) masuk `docs/`, bukan folder milestone yang isinya cuma proses/keputusan spesifik M1.6.
