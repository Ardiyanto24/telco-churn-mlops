# Report — Milestone 1.4: Unit Test untuk Modul Transformasi

## Ringkasan

Milestone 1.4 selesai. Sesuai permintaan user, dilakukan **audit ulang menyeluruh dari nol** terhadap cakupan test M1.2/M1.3 (102 test) — bukan mengasumsikan sudah cukup walau lulus semua. Audit berbasis `pytest-cov --cov-branch` (bukan sekadar ingatan/klaim manual) menemukan branch coverage sebenarnya **91%** (bukan 94% seperti line coverage awal yang menyembunyikan cabang `False` tak teruji), dengan 4 kategori gap konkret. Seluruh gap diisi, `KK3` (uji coba terkontrol) dibuktikan lewat 5 eksperimen sengaja-rusak-lalu-revert, dan GitHub Actions workflow dibuat. Total akhir: **123 test lulus, 100% branch coverage**.

## Kontrak Sumber vs Bukti (KK1-KK3)

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Seluruh fungsi modular punya cakupan test mencakup minimal 1 kasus normal + 1 kasus tepi. | Audit `--cov-branch` (Checkpoint 1, `logs.md`) menemukan 4 gap nyata: `get_feature_names_out()`/`get_feature_names()` 0% coverage di 7 method; 6 cabang defensif "kolom sumber hilang" `FeatureEngineer` tak pernah diuji False; skenario "tidak ada kolom target" `OHEWrapper`/`ScalerWrapper` tak pernah diuji; celah integrasi skema->transform belum pernah dibuktikan. Seluruhnya diisi Checkpoint 2 (21 test baru) — branch coverage naik ke **100%**, dikonfirmasi lewat `pytest --cov-branch` ulang, bukan klaim. |
| **KK2** | Test parity terhadap notebook asli (M1.2) — diaudit ulang, ditemukan sudah memadai (tidak ada gap tambahan di `test_parity_real_artifact.py`). | Diverifikasi tetap lulus sepanjang milestone ini, termasuk saat dipakai sebagai "sensor" tambahan di Checkpoint 3 eksperimen #2 (mutasi `ScalerWrapper` terdeteksi lintas milestone, bukan cuma di test M1.4 sendiri). |
| **KK3** | Uji coba terkontrol (sengaja merusak fungsi) menyebabkan test relevan gagal. | Checkpoint 3, `logs.md` — 5 eksperimen (`FeatureEngineer.tc_residual`, `ScalerWrapper.transform`, `OHEWrapper.drop`, schema `tenure` range, `StructuralEncoder.STRUCTURAL_MAP`), masing-masing dibuktikan MERAH saat rusak dan HIJAU lagi persis setelah revert (`git status --short` kosong dikonfirmasi tiap kali). Tabel bukti lengkap di `logs.md` Checkpoint 3. |
| *(tambahan)* | Konfigurasi CI/CD. | `.github/workflows/test.yml` (Checkpoint 4) — YAML tervalidasi sintaksis, mencerminkan command yang benar-benar dipakai sepanjang milestone ini. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 4 keputusan: (1) audit pakai coverage tooling bukan review manual saja, (2) uji coba terkontrol sampel representatif berisiko tinggi, (3) GitHub Actions default skip test Supabase, (4) audit findings di `logs.md` bukan file terpisah. Klarifikasi awal (audit dari nol vs petakan+isi-gap; GitHub Actions vs platform lain) dijawab user sebelum plan ditulis.

## Perubahan dari Plan Awal

- Jumlah task Checkpoint 2 sesuai perkiraan plan awal ("jumlah ditentukan hasil Task 1") — 4 task konkret (bukan rentang XS-S per gap yang lebih granular seperti dibayangkan awal, karena gap-gap yang ditemukan cukup homogen dalam kategori masing-masing sehingga bisa digabung per kategori, bukan per baris).
- Eksperimen #4 Checkpoint 3 (mutasi `tenure` range) menghasilkan `TypeError` dari internal mock (bukan `AssertionError` yang rapi seperti eksperimen lain) karena efek samping mutasi membuat eksekusi lanjut lebih jauh dari yang diantisipasi test integrasi. Dicatat apa adanya di `logs.md` — tetap bukti valid mutasi terdeteksi, tidak disamarkan jadi kelihatan lebih rapi dari kenyataan.
- Tidak ada revisi assumsi besar seperti M1.2 — dua pertanyaan klarifikasi dijawab lebih dulu sebelum plan ditulis, konsisten pola M1.3.

## Keterbatasan dan Item Terbuka

- **GitHub Actions workflow belum diverifikasi jalan sungguhan** — repo tidak punya remote GitHub sama sekali. Validasi yang dilakukan cuma sintaksis YAML lokal.
- **`SUPABASE_DB_URL` belum dikonfigurasi sebagai GitHub Secret** — konsekuensi dari poin di atas (tidak ada repo GitHub untuk menaruh secret). Test integrasi (`test_parity_real_artifact.py`, `test_raw_schema_supabase.py`) akan auto-skip di CI sampai user push ke GitHub dan menambahkan secret secara manual.
- **Uji coba terkontrol (KK3) hanya mencakup 5 dari total fungsi berisiko** — sesuai Keputusan #2 (sampel representatif, bukan mutasi menyeluruh formal ala `mutmut`). Class passthrough sederhana (`BinaryEncoder`, `ColumnDropper`) tidak diuji dengan cara ini — risikonya dinilai jauh lebih rendah untuk kesalahan diam-diam.
- KT-1 (Milestone 1.6 formal), KT-2, sisa KT-3 — tidak terpengaruh milestone ini.

## Follow-up

- Saat repo di-push ke GitHub (kapan pun itu terjadi), tambahkan `SUPABASE_DB_URL` sebagai Repository Secret supaya CI menjalankan test integrasi juga — instruksi sudah ada sebagai komentar di `.github/workflows/test.yml`.
- Milestone 2.7 (CI/CD dan Verifikasi Parity Otomatis, Orang #2) akan MEMPERLUAS workflow ini (bukan membangun ulang) — gerbang kualitas data dan gerbang deployment ditambahkan di pipeline CI yang sama, sesuai prinsip "infrastruktur bersama" dokumen arsitektur.
