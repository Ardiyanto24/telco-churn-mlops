# Keputusan — Milestone 1.3: Skema dan Validasi Data Input

**Klarifikasi sebelum plan disusun:** empat pertanyaan genuinely-terbuka diajukan ke user sebelum breakdown ditulis (bukan diasumsikan), karena Milestone 1.3 secara eksplisit soal kontrak skema — area yang riskan kalau ditebak sepihak:

1. Target skema batch tetap `telco_customers_synthetic` (snake_case), meski tabel itu masih 0 baris (generator belum aktif) — bukan reconsider ke `telco_customers_source` (PascalCase, yang punya data nyata).
2. Validasi batch (DataFrame) pakai **pandera**, bukan custom hand-rolled.
3. Validasi request real-time pakai **Pydantic**, bukan custom hand-rolled.
4. Konvensi field request real-time: **snake_case, identik nama kolom** (bukan camelCase).

## 1. Constraint per kolom: sumber tunggal dari audit M1.1, bukan didesain ulang

**Keputusan:** Tipe, kategori valid, dan rentang numerik tiap kolom diambil langsung dari `docs/03-notebook-audit/notebook-audit.md` Bagian A (nilai unik hasil EDA Insight 6) dan Bagian H.3 (CHECK constraint `telco_customers_synthetic`): `tenure` int [1,72], `monthly_charges` float >0, `total_charges` float >=0, `senior_citizen` int {0,1}, kolom kategorikal Yes/No/No internet service/No phone service sesuai daftar per kolom, `contract`/`internet_service`/`payment_method` sesuai daftar kategori masing-masing.

**Kenapa:** Bukan keputusan desain baru — sudah ada bukti definitif dari dua sumber (EDA + CHECK constraint database sungguhan, keduanya diverifikasi langsung ke Supabase di Milestone 1.1). Mendesain ulang rentang/kategori dari nol akan mengabaikan bukti yang sudah dikumpulkan dan berisiko tidak konsisten dengan constraint yang sudah berjalan di level database.

## 2. Satu sumber constraint dipakai dua skema, bukan didefinisikan dua kali

**Keputusan:** `src/churn_prediction/schema/constants.py` berisi definisi constraint (kategori valid per kolom, rentang numerik) sebagai satu sumber tunggal. `raw_schema.py` (pandera) dan `request_schema.py` (Pydantic) membaca dari sini — bukan menuliskan ulang daftar kategori/rentang secara independen. Column grouping (`ADDON_COLS`, `BINARY_COLS`, `OHE_COLS`, `STRUCTURAL_COLS`, `NUMERIC_COLS`) di-reuse dari `churn_prediction.transform.constants` (Milestone 1.2) yang sudah ada.

**Kenapa:** Prinsip "satu sumber kebenaran" (Bagian 2 dokumen arsitektur) berlaku juga di sini — KK2 milestone ini eksplisit minta pemetaan yang konsisten antara dua skema; dua definisi independen berisiko *drift* diam-diam (satu diubah, satu lupa). Reuse `transform.constants` mencegah duplikasi lebih lanjut, konsisten dengan struktur yang sudah dibangun Milestone 1.2.

## 3. Dependency baru: pandera dan pydantic, pin langsung (bukan provisional)

**Keputusan:** Tambahkan `pandera` dan `pydantic` ke `dependencies` inti `pyproject.toml` (bukan `dev` — modul skema ini dipakai jalur produksi batch/real-time nanti), dipin ke versi stabil terkini — **bukan** mengikuti pola "provisional sampai DS konfirmasi" seperti pandas/numpy/scikit-learn di Milestone 1.2.

**Kenapa:** Keputusan #2 Milestone 1.2 (dependency provisional) spesifik untuk library yang DIPAKAI DS saat training (risiko training-serving skew kalau versi beda — KT-3, `docs/keputusan-tertunda.md`). `pandera`/`pydantic` adalah library BARU yang kita perkenalkan sendiri untuk validasi produksi — DS tidak pernah memakainya, tidak ada "versi asli" yang perlu ditiru, jadi tidak perlu didekati provisional.

## 4. Cakupan skema request real-time: 19 field fitur saja, tanpa ID/correlation field

**Keputusan:** `request_schema.py` hanya mendefinisikan 19 field yang identik dengan kolom fitur transformasi (`gender, senior_citizen, partner, dependents, tenure, phone_service, multiple_lines, internet_service, online_security, online_backup, device_protection, tech_support, streaming_tv, streaming_movies, contract, paperless_billing, payment_method, monthly_charges, total_charges`). Tidak menambahkan field seperti `customer_id`/`request_id` untuk korelasi request-response.

**Kenapa:** KK milestone ini eksplisit soal "pemetaan field-ke-kolom" untuk fitur model, bukan desain API secara umum — dokumentasi API lengkap (skema request/response, kode error, contoh pemanggilan) adalah output Milestone 3.2 (`mlops-03-deployment-observability.md`). Menambah field ID sekarang berarti menebak keputusan desain API yang belum waktunya, karena belum ada framework/endpoint sungguhan yang dibangun.
