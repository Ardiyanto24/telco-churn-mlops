# Report — Milestone 1.6: Kontrak Skema dengan Sumber Data

## Ringkasan

Milestone 1.6 selesai. Berbeda dari M1.1-1.5 (yang menghasilkan kode `src/`), M1.6 menghasilkan **kesepakatan eksplisit dan terdokumentasi** soal skema tabel sumber PostgreSQL/Supabase — `docs/04-schema-contract/raw-schema-contract.md` (kontrak skema) + `CHANGELOG.md` (jalur komunikasi perubahan). Tiga pertanyaan genuinely-terbuka diklarifikasi ke user sebelum plan ditulis; dua di antaranya (semantik update generator, jalur komunikasi) dijawab lewat rekomendasi standar industri yang diminta eksplisit oleh user, dijelaskan detail, dan dikonfirmasi sebelum jadi keputusan final. Dua item lama di backlog project-wide (`docs/keputusan-tertunda.md` KT-1, KT-2) resmi ditutup; satu item baru (KT-4) ditambahkan dari temuan konkret selama eksekusi.

## Kontrak Sumber vs Bukti (KK1-KK2)

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Skema terdokumentasi diverifikasi cocok dengan struktur tabel sungguhan di PostgreSQL (bukan asumsi dari dokumentasi lama). | Checkpoint 1 (`logs.md`) — query read-only langsung (`information_schema.columns`, `table_constraints`, `pg_constraint`) untuk ketiga tabel (`telco_customers_source`, `telco_customers_synthetic`, `synthetic_generation_runs`), dibandingkan kolom-per-kolom, constraint-per-constraint terhadap `notebook-audit.md` Bagian H. **Hasil: 0 drift** — seluruh 21+2 kolom (source), 20+3 kolom (synthetic), 7 kolom (generation_runs), PK/FK, CHECK constraint, dan row count (594.194/0/0) cocok persis. |
| **KK2** | Ada kesepakatan tertulis (meski sederhana) soal jalur komunikasi perubahan skema ke depan. | Checkpoint 3 (`docs/04-schema-contract/CHANGELOG.md`) — format entry wajib, tabel klasifikasi breaking vs non-breaking (7 skenario konkret), proses git PR, dan kewajiban baca CHANGELOG sebelum memulai pekerjaan bergantung (dicantumkan eksplisit di `raw-schema-contract.md` Bagian 5). Entry pertama (v1) mengaudit M1.1-1.3/1.5 dan mengonfirmasi seluruhnya sudah konsisten kontrak baru ini tanpa perlu perubahan kode. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 5 keputusan: (1) kontrak tabel dua-fase menutup KT-1, (2) semantik update append-only snapshot/SCD Type 2 menutup KT-2 dengan gap `customer_key` ditemukan, (3) jalur komunikasi data contract versioned dengan CHANGELOG, (4) semantik unit/timezone/null didokumentasikan penuh dari bukti yang sudah ada, (5) dokumen kontrak substantif di `docs/04-schema-contract/` bukan `milestones/`. Tiga klarifikasi awal dijawab user sebelum plan ditulis — 2 di antaranya (KT-2, jalur komunikasi) lewat permintaan eksplisit rekomendasi standar industri, dijelaskan detail dalam dua putaran percakapan, lalu dikonfirmasi terpisah sebelum final.

## Perubahan dari Plan Awal

- Tidak ada penyimpangan besar dari plan yang disetujui — seluruh 6 checkpoint dieksekusi persis sesuai urutan yang direncanakan.
- Klarifikasi awal butuh dua putaran (bukan satu) — user meminta penjelasan lebih detail untuk Q1 (kegunaan praktis pilihan tabel) dan Q2 (contoh konkret update in-place vs snapshot) sebelum menjawab, dan meminta rekomendasi eksplisit untuk Q2/Q3 alih-alih memilih dari opsi yang ditawarkan. Ini konsisten dengan pola kerja proyek: tidak memaksakan jawaban ke user yang genuinely belum tahu, dan tetap meminta konfirmasi eksplisit atas rekomendasi sebelum dijadikan keputusan final (bukan diam-diam dianggap disetujui).

## Keterbatasan dan Item Terbuka

- **Gap `customer_key` (KT-4) belum diselesaikan** — migrasi skema database di luar cakupan implementasi M1.6 (dan di luar cakupan seluruh sistem MLOps ini; generator adalah "given"). Dicatat lengkap sebagai follow-up wajib sebelum generator diaktifkan.
- **Trigger aktivasi generator belum bertanggal** — kontrak dua-fase (KT-1) memakai trigger eksplisit ("setelah sistem selesai dibangun"), bukan tanggal pasti. Tidak menghalangi pekerjaan M1.x-3.x berjalan, tapi berarti Fase 2 kontrak tidak bisa diverifikasi jalan sungguhan sampai saat itu tiba.
- **Disiplin git PR untuk perubahan skema (Keputusan #3) adalah proses yang DISEPAKATI, bukan sesuatu yang sudah "diuji" di milestone ini** — akan benar-benar diuji saat kontrak ini pertama kali direvisi (entry CHANGELOG kedua).
- **KT-3 (versi library) tidak terpengaruh milestone ini** — tetap terbuka sebagian untuk xgboost/lightgbm (lihat `docs/keputusan-tertunda.md`).

## Follow-up

- **KT-4** perlu diselesaikan (desain kolom `customer_key`, migrasi skema `telco_customers_synthetic`) sebelum data generator pertama kali diaktifkan/diuji.
- Milestone 2.x/3.x (Orang #2/#3) **wajib membaca** `docs/04-schema-contract/raw-schema-contract.md` + `CHANGELOG.md` sebelum mulai bekerja — kontrak ini jadi rujukan langsung untuk desain query batch DAG (M2.5) dan skema request real-time API (M3.x, selaras `churn_prediction.schema`).
- Ini adalah **milestone terakhir di jalur Orang #1** (`mlops-01-productionization.md`) — dengan M1.1-1.6 selesai, seluruh pekerjaan productionization (audit, modularisasi, skema, unit test, inference service, kontrak sumber data) tuntas. Serah terima ke Orang #2 (`mlops-02-pipeline-orchestration.md`) dan Orang #3 (`mlops-03-deployment-observability.md`) siap dimulai kapan pun user memutuskan melanjutkan.
