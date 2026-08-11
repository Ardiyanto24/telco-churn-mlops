# Keputusan — Milestone 1.1: Audit dan Inventarisasi Notebook

## 1. Sumber primer vs sumber sekunder

**Keputusan:** `tccp-eda.ipynb` dan `tccp-preprocessing-v2.ipynb` diperlakukan sebagai sumber primer (skema data mentah + logika transformasi lengkap). `tccp-modeling-baseline-v2.ipynb`, `tccp-hyperparameter-tuning.ipynb`, `tccp-evaluation.ipynb`, `tccp-xai-gate-1.ipynb`, `tccp-xai-gate-2.ipynb` diperlakukan sebagai sumber sekunder — dipakai untuk cross-check nama fitur final, tipe output model, dan threshold, bukan untuk menggali ulang logika preprocessing.

**Kenapa:** Kelima notebook sekunder memuat artifact `splits.joblib` hasil preprocessing (data sudah numerik, 29 fitur) dan tidak mengulang transformasi mentah→fitur — dikonfirmasi benar lewat audit Bagian E (`notebook-audit.md`): tidak satu pun dari kelima notebook melakukan operasi dataframe baru di luar load `splits.joblib`. Memperlakukannya sebagai sumber sekunder mencegah kerja ganda membaca logika yang sama berkali-kali, sekaligus memastikan satu sumber kebenaran transformasi benar-benar hanya digali dari satu notebook, konsisten dengan prinsip Bagian 2 dokumen arsitektur.

## 2. Struktur file deliverable

**Keputusan (dikoreksi user setelah draf awal):** Deliverable audit teknis ditulis sebagai satu file `docs/03-notebook-audit/notebook-audit.md` — BUKAN di dalam `milestones/1.1-audit-notebook/`. Folder `milestones/<id>-<slug>/` sejak koreksi ini dikhususkan hanya untuk 3 file standar: `decisions.md`, `logs.md`, `report.md`. Dokumen teknis lintas-rujukan (audit, skema, kontrak) ditaruh di `docs/` dengan folder bernomor urut lanjutan (`01-architecture`, `02-implementation-plan`, sekarang `03-notebook-audit`) — folder baru dibuat lagi untuk dokumen referensi lain di kemudian hari, bukan digabung ke `03-notebook-audit` yang sengaja dibiarkan spesifik ke isi audit notebook ini saja. Isi tetap 7 bagian: Skema Data Mentah, Urutan Operasi Preprocessing, Inventaris Fitur (klasifikasi seketika/historis), Kontrak Model, Cross-Check Notebook Sekunder, Dependency Library, Daftar Ambiguitas.

**Kenapa:** Draf awal (sebelum koreksi) menaruh `notebook-audit.md` di dalam folder milestone karena `milestone-plan-template.md` tidak mendikte lokasi file deliverable non-kode. User mengoreksi ini secara eksplisit: folder `milestones/` harus tetap ramping (3 file standar saja per milestone, konsisten dengan `CLAUDE.md`), sementara dokumen substansi yang akan dirujuk lintas milestone (Milestone 1.2, 1.3, 2.2) lebih tepat hidup di `docs/` bersama dua dokumen arsitektur/implementasi lain yang sudah ada di sana. Bagian "Kontrak Model" tetap dipertahankan sebagai bagian ke-4 (di luar rencana awal yang semula 5 bagian) karena audit notebook evaluasi/tuning menghasilkan temuan kontrak (tipe output, threshold, model final) yang cukup material untuk berdiri sendiri.

## 3. Metode eksekusi audit

**Keputusan:** Notebook dibaca langsung (dump JSON→teks via script Python `nb_dump.py` di scratchpad, lalu dibaca dengan Read/Grep tool), bukan lewat sub-agent eksplorasi paralel.

**Kenapa:** Sesi ini sempat menghentikan/menolak pemanggilan sub-agent eksplorasi sebelum breakdown ulang milestone ini disusun. Pengerjaan langsung dipilih agar presisi formula per fitur (Bagian C `notebook-audit.md`) bisa diverifikasi silang antar-notebook secara langsung dalam satu konteks kerja, tanpa menyatukan laporan dari banyak agent terpisah.

## 4. Klasifikasi fitur: seluruhnya INSTANT

**Keputusan:** Seluruh 29 fitur final dan 21 kolom mentah sumbernya diklasifikasikan **INSTANT** (Bagian C `notebook-audit.md`) — tidak ada fitur yang diklasifikasikan HISTORICAL/AGGREGATE.

**Kenapa:** Dataset training (`playground-series-s6e3/train.csv`) adalah snapshot satu-baris-per-pelanggan tanpa kolom timestamp/log kejadian, dan tidak satu pun dari 7 notebook melakukan agregasi lintas baris/waktu/pelanggan untuk menghasilkan fitur model. Ini adalah pembacaan apa adanya dari notebook, **bukan keputusan desain sistem production** — apakah ini akan tetap benar saat PostgreSQL production sungguhan dipakai (mis. apakah `tenure` di production perlu diturunkan dari log kejadian, bukan dibaca langsung sebagai field current-state) sengaja **tidak diputuskan di sini** dan dicatat sebagai gap terbuka (lihat `notebook-audit.md` Ambiguitas G.3, dan `docs/keputusan-tertunda.md`).

## 5. Sumber data production dikonfirmasi: Supabase (PostgreSQL)

**Keputusan:** Data mentah (identik dengan `playground-series-s6e3/train.csv`) sudah diunduh user dan ditaruh di Supabase — inilah PostgreSQL yang dimaksud dokumen arsitektur (Bagian "Pola sumber data"). User juga sudah membangun sistem data generator near-real-time yang mengikuti pola data training, sengaja belum diaktifkan sampai platform MLOps ini selesai. Kredensial akses disimpan user di `.env` (root project, sudah di-gitignore); repo menyediakan `.env.example` sebagai template tanpa nilai rahasia.

**Kenapa:** Ini menjawab sebagian Ambiguitas G.1 (`notebook-audit.md`) — sumber data production BUKAN Kaggle langsung, melainkan salinan identik di Supabase yang dikontrol user. G.3 (klasifikasi seketika/historis) belum sepenuhnya terjawab — perlu verifikasi langsung terhadap skema tabel di Supabase (apakah kolom seperti `tenure` tersimpan sebagai field current-state siap pakai, atau perlu diturunkan dari struktur lain) sebelum ditutup. Pola kredensial `.env`+`.env.example` mengikuti prinsip "rahasia tidak boleh di-hardcode/di-commit" (`CLAUDE.md`).

## 6. Verifikasi Supabase — G.1 terjawab, G.3 diperkuat, G.10 baru muncul

**Keputusan:** Dilakukan query read-only langsung ke Supabase (`psycopg2`, kredensial dari `.env`, tidak pernah dicetak ke output/log/chat) untuk memverifikasi Ambiguitas G.1 dan G.3 secara empiris — bukan hanya berdasar pernyataan user. Hasil didokumentasikan sebagai Bagian H baru di `docs/03-notebook-audit/notebook-audit.md`, BUKAN diputuskan sepihak untuk pertanyaan yang baru muncul (G.10 — tabel `telco_customers_source` vs `telco_customers_synthetic` mana yang jadi kontrak resmi Milestone 1.3) — dicatat sebagai keputusan tertunda di `docs/keputusan-tertunda.md` (KT-1, KT-2) sesuai workflow `CLAUDE.md`, karena bukan wewenang Milestone 1.1 untuk memutuskan kontrak skema.

**Kenapa:** Prinsip verifikasi CLAUDE.md ("jangan menganggap perubahan benar tanpa bukti — query langsung, bukan cuma baca log sendiri") berlaku juga untuk klaim user soal sumber data — pernyataan "data sudah ditaruh di Supabase" perlu dibuktikan lewat query, bukan diterima mentah. Hasilnya: `telco_customers_source` terbukti byte-identik dengan data training (row count, distribusi target, 3 baris sampel pertama cocok persis) — G.1 tuntas. Tapi verifikasi ini juga menyingkap fakta baru yang tidak terlihat dari audit notebook saja (skema `telco_customers_synthetic` beda konvensi nama kolom) — sesuai prinsip "keputusan yang belum saatnya dibuat dicatat sebagai backlog", G.10 TIDAK diputuskan di sini karena akan menyerobot wewenang Milestone 1.3.
