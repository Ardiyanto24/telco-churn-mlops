# Keputusan — Milestone 1.1: Audit dan Inventarisasi Notebook

## 1. Sumber primer vs sumber sekunder

**Keputusan:** `tccp-eda.ipynb` dan `tccp-preprocessing-v2.ipynb` diperlakukan sebagai sumber primer (skema data mentah + logika transformasi lengkap). `tccp-modeling-baseline-v2.ipynb`, `tccp-hyperparameter-tuning.ipynb`, `tccp-evaluation.ipynb`, `tccp-xai-gate-1.ipynb`, `tccp-xai-gate-2.ipynb` diperlakukan sebagai sumber sekunder — dipakai untuk cross-check nama fitur final, tipe output model, dan threshold, bukan untuk menggali ulang logika preprocessing.

**Kenapa:** Kelima notebook sekunder memuat artifact `splits.joblib` hasil preprocessing (data sudah numerik, 29 fitur) dan tidak mengulang transformasi mentah→fitur — dikonfirmasi benar lewat audit Bagian E (`notebook-audit.md`): tidak satu pun dari kelima notebook melakukan operasi dataframe baru di luar load `splits.joblib`. Memperlakukannya sebagai sumber sekunder mencegah kerja ganda membaca logika yang sama berkali-kali, sekaligus memastikan satu sumber kebenaran transformasi benar-benar hanya digali dari satu notebook, konsisten dengan prinsip Bagian 2 dokumen arsitektur.

## 2. Struktur file deliverable

**Keputusan:** Deliverable audit ditulis sebagai satu file `milestones/1.1-audit-notebook/notebook-audit.md` dengan 7 bagian: Skema Data Mentah, Urutan Operasi Preprocessing, Inventaris Fitur (klasifikasi seketika/historis), Kontrak Model, Cross-Check Notebook Sekunder, Dependency Library, Daftar Ambiguitas.

**Kenapa:** `milestone-plan-template.md` tidak mendikte nama file deliverable non-kode. Memisahkan `report.md` (ringkasan hasil + bukti verifikasi, ditulis saat penutupan) dari deliverable teknis itu sendiri (`notebook-audit.md`, dipakai langsung Milestone 1.2/1.3/2.2) supaya milestone berikutnya bisa merujuk satu file spesifik tanpa membongkar laporan penutupan milestone ini. Bagian "Kontrak Model" ditambahkan di luar rencana awal (semula 5 bagian) karena audit notebook evaluasi/tuning menghasilkan temuan kontrak (tipe output, threshold, model final) yang cukup material untuk berdiri sendiri, bukan disisipkan di bagian lain.

## 3. Metode eksekusi audit

**Keputusan:** Notebook dibaca langsung (dump JSON→teks via script Python `nb_dump.py` di scratchpad, lalu dibaca dengan Read/Grep tool), bukan lewat sub-agent eksplorasi paralel.

**Kenapa:** Sesi ini sempat menghentikan/menolak pemanggilan sub-agent eksplorasi sebelum breakdown ulang milestone ini disusun. Pengerjaan langsung dipilih agar presisi formula per fitur (Bagian C `notebook-audit.md`) bisa diverifikasi silang antar-notebook secara langsung dalam satu konteks kerja, tanpa menyatukan laporan dari banyak agent terpisah.

## 4. Klasifikasi fitur: seluruhnya INSTANT

**Keputusan:** Seluruh 29 fitur final dan 21 kolom mentah sumbernya diklasifikasikan **INSTANT** (Bagian C `notebook-audit.md`) — tidak ada fitur yang diklasifikasikan HISTORICAL/AGGREGATE.

**Kenapa:** Dataset training (`playground-series-s6e3/train.csv`) adalah snapshot satu-baris-per-pelanggan tanpa kolom timestamp/log kejadian, dan tidak satu pun dari 7 notebook melakukan agregasi lintas baris/waktu/pelanggan untuk menghasilkan fitur model. Ini adalah pembacaan apa adanya dari notebook, **bukan keputusan desain sistem production** — apakah ini akan tetap benar saat PostgreSQL production sungguhan dipakai (mis. apakah `tenure` di production perlu diturunkan dari log kejadian, bukan dibaca langsung sebagai field current-state) sengaja **tidak diputuskan di sini** dan dicatat sebagai gap terbuka (lihat `notebook-audit.md` Ambiguitas G.3, dan `docs/keputusan-tertunda.md`).
