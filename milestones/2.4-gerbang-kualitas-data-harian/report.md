# Report — Milestone 2.4: Gerbang Kualitas Data Harian

## Ringkasan

Milestone 2.4 selesai — berbeda dari M2.2/M2.3, milestone ini **tidak terdampak** temuan "tidak ada feature store" (memeriksa data mentah langsung, independen dari fitur model) dan menghasilkan kode+infra sungguhan, bukan cuma dokumentasi. Dua keputusan yang sengaja dibiarkan terbuka dokumen arsitektur (Bagian 10: ambang batas kewajaran data) dikonfirmasi user sebelum plan ditulis: metodologi persentase deviasi sederhana (bukan statistik formal — opsi upgrade tetap dibuka), dan perilaku bertingkat (stop untuk pelanggaran parah, flag untuk ringan).

Modul `src/churn_prediction/quality/` dibangun: `baseline.py` (riwayat rolling di Postgres, tabel baru `quality.gate_run_history`, role least-privilege `quality_gate`), `checks.py` (3 pure function pemeriksaan), `gate.py` (orkestrasi). Seluruh verifikasi memakai uji coba terkontrol (data sintetis dikombinasikan statistik real `telco_customers_source`) — sesuai KK asli milestone sendiri, BUKAN kompromi darurat.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Penyimpangan volume/nilai buatan (uji coba terkontrol) berhasil terdeteksi dan menghentikan/menandai run sebelum sampai ke scoring. | `tests/quality/test_gate.py`: volume disuntik anjlok 90% → verdict `stop`; NULL disuntik naik 15% pada kolom fitur → verdict `stop`; distribusi kategori digeser 15 poin → verdict `flag` (pelanggaran ringan, bukan parah) — membuktikan mekanisme bertingkat, bukan cuma biner. Seluruh 5 skenario `pytest tests/quality/test_gate.py -v` → **5 passed**, dijalankan terhadap `quality.gate_run_history` SUNGGUHAN di Supabase, bukan mock. |
| **KK2** | Kondisi data normal (fluktuasi wajar) tidak memicu false alert. | `test_normal_data_passes_no_false_alert` — data hari ini dengan fluktuasi kecil (proporsi kontrak 50%→51%) dibanding baseline seeded → verdict `pass`. Juga `test_insufficient_baseline_history_does_not_false_flag` — baseline <3 run tidak memicu false-flag (dilewati dengan catatan, bukan dianggap anomali). |

`pytest tests/ -q` penuh: **163 passed** (138 sebelumnya + 25 baru), tidak ada regresi.

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 5 keputusan: (1) metodologi deviasi sederhana dengan ambang konkret per check (opsi statistik formal dicatat sebagai upgrade masa depan, bukan ditolak permanen); (2) perilaku bertingkat stop/flag; (3) **keterbatasan eksplisit**: verifikasi memakai uji coba terkontrol karena `telco_customers_source` cuma 1 event loading (bukan data harian asli) — dicatat, bukan disembunyikan; (4) tabel riwayat baseline baru (`quality.gate_run_history`, schema `quality`, append-only) + role least-privilege terpisah, eksplisit BEDA dari feature store M2.2 (metrik kualitas data, bukan fitur model); (5) 18 kolom input fitur model yang dicek (rujuk M2.2, tidak diulang).

## Perubahan dari Plan Awal

Tidak ada penyimpangan dari plan yang disetujui — 3 checkpoint dieksekusi sesuai urutan. Satu detail teknis muncul saat eksekusi (tidak mengubah scope): percobaan pertama skrip verifikasi provisioning mencoba `DELETE` baris probe lewat koneksi `quality_gate` dan gagal (`InsufficientPrivilege`) — ini justru BUKTI scoping least-privilege bekerja benar (role sengaja tanpa privilege DELETE, tabel append-only), bukan bug; skrip verifikasi diperbaiki untuk cleanup lewat koneksi admin.

## Keterbatasan dan Item Terbuka

- **Ambang batas (deviasi persentase) belum tervalidasi terhadap data harian asli** — `telco_customers_source` cuma 1 event loading, `telco_customers_synthetic` masih 0 baris. Ambang batas konkret di `decisions.md` adalah estimasi awal yang wajar (informed oleh statistik real 594.194 baris), BUKAN hasil kalibrasi terhadap pola fluktuasi harian sungguhan. Ini keterbatasan provisional (pola sama KT-3), bukan cacat desain.
- **Modul belum dipanggil dari mana pun secara production** — `run_gate()` siap dipakai tapi belum diintegrasikan ke DAG batch (M2.5, belum dibangun) maupun pipeline CI (M2.7, belum dibangun). Ini SESUAI scope M2.4 (bangun mekanisme reusable, bukan mengintegrasikannya — lihat `mlops-02-pipeline-orchestration.md` M2.7 yang eksplisit menyebut "mengintegrasikan pemeriksaan dari Milestone 2.4 ke pipeline CI/CD" sebagai pekerjaan M2.7 sendiri).
- Opsi upgrade ke metodologi statistik formal (z-score/chi-square) tetap terbuka, dicatat eksplisit di `decisions.md` — trigger: riwayat run cukup banyak dan/atau data harian asli sudah mengalir.

## Follow-up

- **Milestone 2.5 (Batch Scoring DAG)** akan memanggil `run_gate()` sebagai salah satu task DAG, memakai 18 kolom fitur model (M2.2) sebagai `numeric_columns`/`categorical_columns`.
- **Milestone 2.7 (CI/CD)** akan mengintegrasikan `run_gate()` sebagai gerbang CI, bukan cuma task DAG terisolasi — sesuai deskripsi asli M2.7.
- **Kalibrasi ulang ambang batas** direkomendasikan begitu data harian asli tersedia (generator diaktifkan, Fase 2 KT-1) — cukup riwayat run sungguhan untuk menilai apakah ambang 20%/50% (volume) dan 10pt/30pt (distribusi) terlalu sensitif atau terlalu tumpul terhadap variasi harian nyata.
