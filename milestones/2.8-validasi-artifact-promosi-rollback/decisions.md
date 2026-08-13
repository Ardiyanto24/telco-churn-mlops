# Decisions — Milestone 2.8: Validasi Artifact, Promosi, dan Rollback Versi Model

## Temuan Sebelum Plan Ditulis

Sebagian besar mekanisme SUDAH ADA sejak Milestone 2.1 — `docs/05-model-registry-contract/model-registry-contract.md` sudah mencadangkan alias `challenger` eksplisit "belum dipakai sampai M2.8 dikerjakan", dan dua script CLI (`scripts/register_production_model.py`, `scripts/promote_active_alias.py`) sudah dibangun dan disebut eksplisit "dipakai lagi... sebelum M2.8". M2.8 TIDAK membangun mekanisme alias dari nol — pekerjaannya memasang dua gerbang validasi (Bagian 5.5 dokumen arsitektur) di depan mekanisme yang sudah ada, plus verifikasi end-to-end sungguhan.

## Klarifikasi Sebelum Plan Disusun

1. **Kandidat uji dibuat dari model SAMA, threshold BEDA** (0.5 uji vs 0.6238 produksi) — bukan training ulang. Dikonfirmasi user setelah penjelasan detail (opsi threshold-beda vs duplikat-persis).
2. **Kriteria verifikasi-sebelum-promosi**: (a) tidak ada exception/NaN pada sampel real — wajib; (b) delta churn_rate vs ambang provisional — verdict pass/flag, TIDAK auto-blocking. Dikonfirmasi user.

## Keputusan Teknis

### 1. Sanity check dipasang DI DALAM `register_model()`, bukan cuma di script pemanggil

**Keputusan:** `sanity_check_bundle()` (`artifact_validation.py`) dipanggil otomatis di awal `register_model()` (`registry.py`) — `ValueError` sebelum `mlflow.pyfunc.log_model()` kalau gagal.

**Kenapa:** Bagian 5.5 dokumen arsitektur eksplisit: sanity check adalah syarat "sebelum registrasi ke MLflow... sebagai kandidat versi" — memasangnya di DALAM fungsi registrasi menjamin SETIAP jalur (script mana pun, sekarang atau masa depan) otomatis terlindungi, tidak bergantung ingat memanggilnya secara terpisah di tiap pemanggil.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Sanity check sebagai langkah terpisah yang HARUS dipanggil manual sebelum `register_model()`** — DITOLAK: rapuh, bisa terlupa di script/pemanggil baru di masa depan, tidak benar-benar "gerbang" kalau bisa dilewati begitu saja.

### 2. Input uji sanity check: sintetis, bukan data production

**Keputusan:** `sanity_check_bundle()` pakai baris uji sintetis (pola sama `_valid_row()` M1.5), TIDAK butuh akses DB.

**Kenapa:** Bagian 5.5 minta "sejumlah input uji" (bukan data production) untuk gerbang PERTAMA — beda tujuan dari gerbang KEDUA (verifikasi-sebelum-promosi) yang eksplisit minta "sampel data production terkini". Membuat sanity check offline-capable/cepat, tidak bergantung state DB.

**Opsi yang Dipertimbangkan tapi Ditolak:** **Pakai sampel real untuk sanity check juga** — DITOLAK: mengaburkan dua gerbang yang Bagian 5.5 eksplisit minta dipisah ("jangan ditukar"), menambah dependency DB yang tidak perlu untuk gerbang yang seharusnya bisa jalan offline.

### 3. Kandidat uji: model sama, threshold berbeda (0.5 vs 0.6238)

**Keputusan:** `scripts/register_candidate_model.py` registrasi `model_final.joblib`+`preprocessor.joblib` SAMA PERSIS (tidak training ulang), threshold 0.5 (ditandai jelas "UJI" di kode+output), tag alias `challenger`.

**Kenapa:** Dikonfirmasi user setelah penjelasan. Tidak boleh training ulang (`CLAUDE.md`) — satu-satunya cara mendapat kandidat yang GENUINELY berbeda outputnya (bukan duplikat trivial) tanpa training adalah threshold berbeda: `churn_probability` identik (model sama), `churn_label` berbeda untuk baris borderline. Pola SAMA persis sudah dipakai `tests/inference/test_registry.py` (M1.5) — bukan pendekatan baru, reuse preseden yang sudah teruji.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Duplikat persis (threshold sama)** — DITOLAK user: verifikasi-sebelum-promosi jadi trivial lolos (prediksi identik byte-per-byte), tidak menguji skenario "kandidat genuinely berbeda dari champion".

### 4. Kriteria verifikasi-sebelum-promosi: pola + tanpa-error, provisional

**Keputusan:** `scripts/verify_before_promotion.py` — dua syarat: (a) WAJIB tidak ada exception/NaN pada sampel real (`telco_customers_source`, ukuran 1000 baris); (b) `|churn_rate(challenger) - churn_rate(champion)|` < 20 poin persentase PROVISIONAL — verdict `pass`/`flag`, TIDAK exit non-zero untuk flag (bukan gerbang otomatis blocking).

**Kenapa:** Dikonfirmasi user. Kandidat SECARA DESAIN berbeda dari champion (beda dari parity test M2.5/M2.7 yang harus identik) — kriteria "harus sama persis" tidak masuk akal di sini. Bagian 5.5 eksplisit: "bukan proses otomatis yang kompleks... cukup langkah verifikasi SADAR" — verdict jadi MASUKAN untuk keputusan manusia, bukan gerbang CI yang menggagalkan build. Ambang 20pp PROVISIONAL (pola sama M2.4) — belum ada riwayat data production yang cukup untuk kalibrasi lebih presisi.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Cukup tanpa-error/NaN saja (skip perbandingan pola)** — DITOLAK user: terlalu dekat ke "sanity check lagi", tidak memenuhi tujuan berbeda Bagian 5.5 (verifikasi sebelum promosi harus melihat POLA hasil, bukan cuma "tidak crash").
- **Ambang statistik formal (mis. Kolmogorov-Smirnov test)** — DITOLAK user: jauh lebih banyak kerja implementasi, sulit diverifikasi benar tanpa riwayat data production yang banyak (baru ada 1 snapshot statis `telco_customers_source`).

### 5. Verifikasi-sebelum-promosi dijalankan sungguhan — hasil PASS, delta 6.30pp

**Keputusan (temuan, bukan pilihan):** Dijalankan terhadap registry+data real: champion (threshold 0.6238) churn_rate 31.20%, challenger (threshold 0.5) churn_rate 37.50%, delta 6.30 poin persentase — di bawah ambang 20pp, verdict PASS.

**Kenapa:** Bukti konkret, bukan diasumsikan — dicatat apa adanya di logs.md terlepas hasilnya pass atau flag (kebetulan PASS di run ini, tapi metodologi TIDAK bergantung hasil tertentu).

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada — ini hasil pengukuran, bukan keputusan desain.

### 6. Uji coba terkontrol promosi+rollback dijalankan terhadap registry PRODUKSI sungguhan

**Keputusan:** `champion` benar-benar dipindah ke versi 2 (challenger) sesaat, DAG dijalankan nyata (`limit=50`), lalu di-rollback ke versi 1, DAG dijalankan nyata lagi — BUKAN simulasi/mock.

**Kenapa:** Konsisten prinsip project "uji coba terkontrol terhadap infrastruktur real" yang sudah dipakai M2.4-2.7 (bukan cuma unit test dengan mock). Risiko diterima sadar: registry produksi SEMENTARA menunjuk versi uji (threshold 0.5) selama beberapa detik sampai rollback — dampak minimal karena tidak ada trafik produksi nyata berjalan bersamaan (generator belum aktif, real-time API belum ada, konsisten kondisi M2.5/M2.6/M2.7). Registry berakhir di state benar (`champion`=versi 1, diverifikasi eksplisit) sebelum lanjut dokumentasi.

**Opsi yang Dipertimbangkan tapi Ditolak:** **Uji di tracking URI SQLite terisolasi (pola `tmp_path` test M1.5)** — tidak dipertimbangkan serius untuk verifikasi UTAMA milestone ini: tidak membuktikan mekanisme bekerja terhadap registry+DAG PRODUKSI sungguhan (yang justru inti KK2/KK3 M2.8 — "run DAG BERIKUTNYA" tersirat DAG produksi nyata), meski tetap dipakai untuk unit test cepat (Checkpoint 1/2).

### 7. KK4 (verifikasi real-time API) di luar cakupan M2.8

**Keputusan:** Tidak ada pekerjaan tambahan untuk memverifikasi sisi real-time API — dicatat sebagai follow-up di report.md, BUKAN keputusan tertunda baru.

**Kenapa:** Teks KK4 sumber sendiri eksplisit: "verifikasi lintas pekerjaan, dijadwalkan bersama Milestone terkait di `mlops-03-deployment-observability.md`" — sudah dijadwalkan secara eksplisit ke M3.x oleh dokumen sumber, bukan genuinely belum diputuskan (beda dari kriteria `docs/keputusan-tertunda.md`).

**Opsi yang Dipertimbangkan tapi Ditolak:** Tidak ada — forced by teks KK sumber sendiri.
