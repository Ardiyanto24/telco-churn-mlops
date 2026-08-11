# Keputusan — Milestone 1.4: Unit Test untuk Modul Transformasi

**Klarifikasi sebelum plan disusun:** Output milestone ini (unit test kasus normal+tepi, test parity terhadap notebook asli, kasus ditolak validasi skema) secara literal tumpang tindih dengan yang sudah dikerjakan Milestone 1.2 (31 test) dan 1.3 (69 test) — total 102 test lulus. Ditanyakan ke user apakah cukup memetakan yang sudah ada + isi gap (CI/CD, uji coba terkontrol), atau audit ulang menyeluruh dari nol. **User memilih audit ulang menyeluruh dari nol** — tidak mengasumsikan 102 test yang ada sudah cukup walau lulus semua. Platform CI/CD: **GitHub Actions**.

## 1. Audit dari nol memakai coverage tooling, bukan review manual saja

**Keputusan:** Tambah `pytest-cov` ke `dev` dependencies. Checkpoint 1 menjalankan `pytest --cov=churn_prediction --cov-report=term-missing` untuk dapat angka objektif per file/baris, disilangkan dengan checklist manual per fungsi (KK1 minta "minimal 1 normal + 1 tepi", bukan cuma persentase baris — coverage tool tidak bisa membedakan "test tepi" vs "test normal" dengan sendirinya).

**Kenapa:** User eksplisit minta "dari nol", bukan percaya pada ingatan bahwa M1.2/M1.3 "sudah lengkap". Coverage tool memberi bukti terukur (baris mana yang tidak pernah dieksekusi test manapun) yang tidak bisa didapat dari membaca ulang test secara manual saja.

## 2. Uji coba terkontrol (KK3): sampel representatif berisiko tinggi, bukan seluruh fungsi

**Keputusan:** "Sengaja merusak fungsi" dilakukan pada 4-5 fungsi berisiko tinggi (formula matematis `FeatureEngineer` yang menghasilkan `tc_residual`/`monthly_to_total_ratio`, `ScalerWrapper`, `OHEWrapper`, dan minimal 1 validator skema) — bukan mengulang untuk ke-7 class transform + 2 modul schema.

**Kenapa:** KK3 minta bukti METODOLOGI test efektif (test benar-benar mendeteksi regresi), bukan mutasi menyeluruh tiap baris kode (itu cakupan tool mutation-testing formal seperti `mutmut`, di luar cakupan milestone ini). Fungsi dengan logika formula/matematis paling berisiko salah diam-diam (hasil tetap jalan, angka salah) — itu yang paling penting dibuktikan test-nya benar-benar sensitif terhadap perubahan. Class passthrough sederhana (`ColumnDropper`, `BinaryEncoder`) risikonya jauh lebih rendah untuk kesalahan diam-diam.

## 3. GitHub Actions: jalankan hanya test yang tidak butuh Supabase, secara default

**Keputusan:** Workflow `.github/workflows/test.yml` menjalankan `pytest` apa adanya (bukan flag khusus) — test yang butuh `SUPABASE_DB_URL` (integration test) sudah auto-skip lewat `pytest.mark.skipif` yang ada sejak M1.2/M1.3 kalau env var tidak diset. Repo belum punya GitHub remote, jadi `SUPABASE_DB_URL` sebagai GitHub Secret TIDAK dikonfigurasi sekarang — didokumentasikan sebagai langkah manual user kalau nanti repo di-push ke GitHub dan ingin CI menjalankan test integrasi juga.

**Kenapa:** Ini konsekuensi praktis, bukan keputusan terbuka — tidak ada remote/secret infrastructure untuk dikonfigurasi saat ini. Auto-skip yang sudah ada (dari M1.2/M1.3) berarti tidak perlu logic tambahan di CI untuk memisahkan unit vs integration test.

## 4. Audit findings ditulis di `logs.md`, bukan file baru terpisah

**Keputusan:** Hasil audit (checklist coverage per fungsi, gap yang ditemukan) dicatat sebagai bagian narasi `logs.md` Checkpoint 1 — bukan file audit terpisah di `docs/` atau file ke-4 di folder milestone.

**Kenapa:** Konsisten dengan koreksi user di Milestone 1.1 — folder `milestones/<id>-<slug>/` dikhususkan hanya untuk `decisions.md`/`logs.md`/`report.md`. Audit ini bersifat proses-verifikasi khusus M1.4 (bukan dokumen substantif yang akan dirujuk milestone lain seperti `notebook-audit.md`), jadi cukup sebagai catatan proses di `logs.md`.
