# Report — Milestone 1.1: Audit dan Inventarisasi Notebook

## Ringkasan

Milestone 1.1 selesai. Ketujuh notebook yang diserahkan Data Scientist (`notebook/tccp-eda.ipynb`, `tccp-preprocessing-v2.ipynb`, `tccp-modeling-baseline-v2.ipynb`, `tccp-hyperparameter-tuning.ipynb`, `tccp-evaluation.ipynb`, `tccp-xai-gate-1.ipynb`, `tccp-xai-gate-2.ipynb`) sudah diaudit tanpa mengubah kode apa pun. Deliverable utama: [`docs/03-notebook-audit/notebook-audit.md`](../../docs/03-notebook-audit/notebook-audit.md) — dokumen tunggal berisi skema data mentah, urutan operasi preprocessing, inventaris 29 fitur final (diklasifikasikan seketika/historis), kontrak model (tipe output, threshold, artifact), cross-check notebook sekunder, dependency library, dan 9 item ambiguitas untuk Data Scientist.

## Kontrak Sumber vs Bukti (KK1-KK3)

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Setiap fitur yang dipakai model punya definisi perhitungan eksplisit dan sudah diklasifikasikan seketika/historis. | `notebook-audit.md` Bagian C — tabel C.1-C.5 mencakup seluruh 29 fitur final, masing-masing dengan formula eksak + kolom mentah input + label klasifikasi. Total baris tabel = 29, cocok dengan `X_train_proc.shape[1]==29` yang tercetak di notebook (bukti langsung, bukan turunan). Seluruh 29 fitur terklasifikasi **INSTANT** — tidak ada baris berstatus kosong/belum jelas. |
| **KK2** | Tidak ada langkah preprocessing berstatus "tidak yakin apakah dipakai atau kode mati" — semua sudah dikonfirmasi. | `notebook-audit.md` Bagian B — seluruh 6 step pipeline (`FeatureEngineer→ColumnDropper→StructuralEncoder→BinaryEncoder→OHEWrapper→ScalerWrapper`) dikonfirmasi lewat kombinasi kode class + output validasi otomatis notebook (cell 25, 7/7 assertion lulus). Tidak ditemukan sel mati di `tccp-preprocessing-v2.ipynb` (33 cell, linear, konsisten dengan diagram alur di cell pertama). Item yang sifatnya "tidak sepenuhnya jelas" (mis. versi library, identitas sumber data) dipindahkan eksplisit ke Bagian G (Ambiguitas) — bukan dibiarkan tercecer sebagai status tak terjawab di Bagian B/C. |
| **KK3** | Dokumen ini bisa dipakai langsung sebagai acuan Milestone 1.2 tanpa perlu membuka ulang notebook dari nol. | Diverifikasi lewat review end-to-end `notebook-audit.md` sebagai reviewer eksternal (Task 13): setiap keputusan modularisasi yang akan diambil Milestone 1.2 (urutan step, formula per fungsi, parameter encoder/scaler, kontrak `preprocessor.joblib`) sudah tersedia langsung di Bagian B-D tanpa perlu rujukan balik ke file notebook. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 4 keputusan: (1) sumber primer vs sekunder, (2) struktur file deliverable, (3) metode eksekusi audit (baca langsung, bukan sub-agent), (4) klasifikasi seluruh fitur sebagai INSTANT (keputusan tambahan yang muncul saat eksekusi, di luar 3 keputusan awal di plan — dicatat sebagai temuan pembacaan notebook, bukan keputusan desain sistem).

## Perubahan dari Plan Awal

- Struktur deliverable bertambah dari 5 bagian (rencana awal) menjadi 7 bagian — ditambahkan Bagian D (Kontrak Model) dan pemisahan Bagian E (Cross-Check) dari Bagian F (Dependency) karena volumenya cukup besar untuk berdiri sendiri.
- Task 8-10 (notebook sekunder) tidak seluruhnya dibaca cell-per-cell penuh seperti Task 7 — sebagian besar diverifikasi lewat `grep` bertarget terhadap dump teks notebook (nama fitur, threshold, artifact) karena konten intinya (model/metrik/nama fitur) sudah cukup untuk dikonfirmasi tanpa membaca ulang seluruh boilerplate kode Optuna/WandB yang berulang pola dengan notebook lain. Tidak mengurangi kelengkapan bukti KK1-KK3.
- Plan awal menetapkan commit per checkpoint (6 commit). Karena seluruh 14 task dikerjakan menerus dalam satu sesi tanpa jeda alami antar-checkpoint (tidak ada file yang ditulis lalu didiamkan sebelum checkpoint berikutnya), keempat file deliverable ditulis sekaligus di akhir dan di-commit sebagai **satu commit tunggal** untuk menghindari histori git yang dipecah artifisial (commit kosong/berurutan tanpa jeda kerja nyata di antaranya). Dicatat di sini secara eksplisit sebagai penyimpangan dari pola commit-per-checkpoint yang dipakai milestone lain.
- **Koreksi pasca-penutupan:** draf pertama milestone ini menaruh `notebook-audit.md` di dalam `milestones/1.1-audit-notebook/`. User mengoreksi: folder `milestones/` khusus 3 file standar (`decisions.md`/`logs.md`/`report.md`); deliverable teknis dipindah ke `docs/03-notebook-audit/notebook-audit.md`. Lihat `decisions.md` #2 (revisi) dan `logs.md` bagian "Koreksi Pasca-Penutupan" untuk detail lengkap.

## Keterbatasan dan Item Terbuka

Sepuluh ambiguitas didaftarkan di `docs/03-notebook-audit/notebook-audit.md` Bagian G (G.10 ditambahkan setelah verifikasi Supabase — lihat Bagian H dokumen yang sama).

- **G.1 — TERJAWAB.** Verifikasi langsung ke Supabase (query `psycopg2` read-only) membuktikan `telco_customers_source` byte-identik dengan data training: row count sama (594.194), distribusi `Churn` sama, 3 baris sampel pertama cocok persis dengan output notebook. Sumber data production = Supabase, bukan Kaggle langsung.
- **G.3 — diperkuat, belum 100% tertutup.** Terbukti hanya ada 3 tabel di seluruh project Supabase, tidak ada satu pun tabel log/riwayat kejadian — memperkuat klasifikasi INSTANT-semua. Yang belum terjawab: apakah baris pelanggan akan di-update in-place seiring waktu atau selalu snapshot baru (generator belum pernah dijalankan, belum bisa diobservasi). Dicatat sebagai KT-2 di `docs/keputusan-tertunda.md`.
- **G.10 — baru, material.** `telco_customers_source` (PascalCase, statis) dan `telco_customers_synthetic` (snake_case, target generator, saat ini kosong) punya konvensi nama kolom berbeda untuk data yang secara semantik sama. Milestone 1.3 perlu memutuskan tabel/konvensi mana yang jadi kontrak resmi. Dicatat sebagai KT-1 di `docs/keputusan-tertunda.md` — **sengaja tidak diputuskan di Milestone 1.1** karena bukan wewenangnya.

Tujuh ambiguitas sisanya (G.2, G.4-G.9) berdampak lebih kecil/administratif dan tidak memblokir dimulainya Milestone 1.2.

## Follow-up

- G.1 dan G.3 sudah diverifikasi terhadap Supabase (lihat Bagian H `notebook-audit.md`) — tidak ada follow-up tersisa untuk keduanya di lingkup Milestone 1.1.
- **KT-1 (G.10)** dan **KT-2 (sisa G.3)** perlu diputuskan pemilik Milestone 1.3/1.6 sebelum kontrak skema data mentah dikunci — lihat `docs/keputusan-tertunda.md`.
- **KT-3 (G.2, versi library)** perlu dijawab sebelum Milestone 1.2 mengunci `requirements.txt`/`pyproject.toml` secara final — sementara ini Milestone 1.2 bisa mulai dengan versi library terkini yang kompatibel dan menandai sebagai provisional sampai DS mengonfirmasi.
