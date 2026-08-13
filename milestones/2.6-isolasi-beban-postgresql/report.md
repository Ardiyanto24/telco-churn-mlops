# Report — Milestone 2.6: Isolasi Beban terhadap PostgreSQL

## Ringkasan

Milestone 2.6 membangun harness pengukuran (`orchestration/load_test/concurrent_readers.py`) untuk menjawab pertanyaan Bagian 6.3 dokumen arsitektur: apakah beban batch scoring DAG (M2.5) mendegradasi performa baca bergaya real-time API. Karena real-time API (M3.x) belum dibangun dan tidak ada feature store (M2.2, DITUTUP), dua proxy consumer disimulasikan — resolusi alias model (MLflow) dan query agregat gaya dashboard monitoring.

Hasilnya konklusif dan bermakna: **satu consumer (dashboard aggregate) menunjukkan degradasi p95 nyata (+210%) yang berkorelasi jelas dengan fase tulis batch M2.5**, sementara consumer lain (resolusi alias model) tidak terdampak sama sekali. Sesuai arahan eksplisit user, verdict formal "apakah ini wajar untuk real-time API" TIDAK disimpulkan sekarang (belum ada SLA nyata) — dicatat sebagai keputusan tertunda (KT-5), begitu juga kandidat mitigasi paling menyasar akar masalah (KT-6).

Tiga bug ditemukan+diperbaiki: deadlock di script pengukuran sendiri (Checkpoint 3, bug baru murni kode milestone ini), pencemaran baseline gerbang kualitas data M2.4 yang berulang (Checkpoint 3, root cause identik M2.5, kali ini dipicu validasi milestone ini sendiri), dan bug laten di `tests/orchestration/test_batch_scoring.py` (M2.5) yang tidak benar-benar memuat `.env` ke `os.environ` (Checkpoint 5, ditemukan saat verifikasi "tidak ada regresi").

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Simulasi baca bergaya real-time API bersamaan job batch menunjukkan latensi wajar dibanding baseline. | **DITERIMA SEBAGIAN, sesuai arahan eksplisit user.** Harness pengukuran + angka nyata tersedia lengkap (baseline vs bersamaan, delta, korelasi per fase — lihat `logs.md`). Consumer A: TIDAK ada degradasi berarti (p50 delta -0.2%, p95 -9.7%). Consumer B: degradasi nyata (p50 +12.0%, p95 **+210.5%**), terkonsentrasi di fase `write`. **Verdict formal "wajar/tidak" TIDAK disimpulkan** — real-time API (M3.x) belum dibangun, tidak ada SLA nyata untuk dijadikan acuan pasti. Dicatat sebagai **KT-5** (`docs/keputusan-tertunda.md`). |
| **KK2** | Strategi mitigasi terdokumentasi beserta alasan pemilihannya. | **DIPENUHI PENUH.** Dievaluasi berdasarkan bukti Checkpoint 3 (bukan default): index pada `model_version` ditolak (tidak menyasar akar masalah — kontensi write-lock, bukan query plan; tidak ada manfaat terukur pada 1 nilai distinct saat ini). Commit bertahap pada `write_predictions` (mitigasi paling menyasar akar masalah) ditolak UNTUK SEKARANG — trade-off nontrivial terhadap jaminan all-or-nothing M2.5, belum ada trafik nyata yang dirugikan. Dicatat sebagai **KT-6**. Keputusan: TIDAK ada mitigasi tambahan diterapkan sekarang, didukung data konkret — lihat `decisions.md` Keputusan #5. |

`pytest tests/ -q` penuh: **170 passed** (sama seperti penutupan M2.5, harness M2.6 sengaja bukan pytest permanen — lihat Keputusan #3). Sempat merah (168 passed, 2 errors) di tengah verifikasi karena bug ketiga (lihat di bawah), hijau kembali setelah diperbaiki.

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 8 keputusan: (1) proxy dua consumer (bukan feature store/telco_customers_source), (2) reuse kredensial existing tanpa role baru, (3) harness sekali-pakai bukan pytest permanen, (4) temuan degradasi Consumer B vs Consumer A, (5) tidak ada mitigasi tambahan sekarang (didukung bukti), (6) verdict KK1 ditunda ke KT-5, (7) dua bug operasional ditemukan+diperbaiki (deadlock script, pencemaran baseline gerbang kualitas berulang), (8) bug ketiga: `tests/orchestration/test_batch_scoring.py` (M2.5) tidak memuat `.env` ke `os.environ` dengan benar. Plus temuan konflik dokumen M3.x (feature store, tidak diubah, bukan wewenang milestone ini).

## Perubahan dari Plan Awal

- **Task 8 (run skala penuh) butuh DUA percobaan**, bukan satu seperti direncanakan — percobaan pertama gagal karena dua bug (gerbang kualitas STOP akibat baseline tercemar; deadlock script akibat `stop_event` tidak terjamin ter-set saat flow gagal). Keduanya diperbaiki sebelum percobaan kedua yang berhasil bersih. Tidak disembunyikan — dicatat detail lengkap di `logs.md` konsisten prinsip "log adalah catatan peristiwa, bukan hasil yang dipoles".
- **Metodologi ambang batas KK1 berubah dari rencana** — plan awal menyiapkan tiga opsi metodologi threshold (deviasi relatif provisional, deskriptif, absolut) untuk diajukan ke user; user memilih opsi KEEMPAT yang lebih fundamental (tunda verdict sepenuhnya sebagai keputusan tertunda, bukan pilih salah satu metodologi threshold). Plan diikuti secara struktur (harness + pengukuran tetap dibangun penuh), tapi kesimpulan akhirnya berbeda dari yang diantisipasi plan.
- **Temuan mitigasi lebih spesifik dari yang diantisipasi plan** — plan mengantisipasi kemungkinan index baru pada `model_version` sebagai kandidat mitigasi; data nyata menunjukkan akar masalah sebenarnya adalah kontensi transaksi tulis panjang (bukan index), menghasilkan KT-6 (commit bertahap) yang tidak diantisipasi eksplisit di plan awal.
- **Checkpoint 5 (verifikasi akhir) menemukan bug ketiga yang tidak diantisipasi plan** — `pytest tests/ -q` penuh awalnya merah (2 error) karena bug laten di file test M2.5 (`test_batch_scoring.py`), bukan regresi dari kode M2.6. Diperbaiki dua tahap (fix pertama parsial kurang, fix kedua tuntas) sebelum full suite kembali hijau (170 passed) dan checkpoint ini dianggap selesai.
- Selebihnya, seluruh 5 checkpoint dan struktur task dieksekusi sesuai urutan yang direncanakan.

## Keterbatasan dan Item Terbuka

- **Verdict KK1 formal belum ada** (KT-5) — data pengukuran nyata tersedia lengkap, tapi kesimpulan "wajar atau tidak untuk real-time API" menunggu M3.x punya SLA nyata.
- **Kandidat mitigasi akar masalah (commit bertahap `write_predictions`) belum diterapkan** (KT-6) — trade-off terhadap jaminan korektnes M2.5, ditunda sampai ada trafik nyata yang benar-benar dirugikan.
- **Pencemaran baseline gerbang kualitas data adalah risiko operasional BERULANG, bukan sepenuhnya "sudah diperbaiki"** — fix M2.5 (reset manual) terbukti hanya solusi sekali-pakai; masalah kambuh di M2.6 dipicu validasi milestone ini sendiri. **Peringatan eksplisit untuk M2.7 (CI/CD) dan M2.8**: setiap run skala kecil (test, validasi, smoke test) terhadap `telco_customers_source` berpotensi mencemari baseline untuk run skala besar berikutnya — cek `quality.gate_run_history` sebelum run skala penuh apa pun, jangan asumsikan baseline bersih.
- **Angka timing fase (extract/score) menunjukkan variasi run-to-run yang signifikan** dibanding baseline M2.5 (extract 17,7s vs ~45s; score 145,7s vs ~265s) — dicatat sebagai temuan, BUKAN angka final tetap; fase `write` (paling relevan untuk milestone ini) jauh lebih stabil (244,3s vs ~241s M2.5).
- **KD-1 (Prefect Managed + LightGBM) tetap berlaku** — run skala penuh milestone ini WAJIB lokal, konsisten preseden M2.5.

## Follow-up

- **Milestone 2.7 (CI/CD)** — WAJIB baca peringatan pencemaran baseline gerbang kualitas data (di atas) sebelum merancang gerbang CI yang menyentuh `telco_customers_source`. Juga perlu pertimbangkan KD-1 untuk runner CI yang memuat model.
- **Milestone 2.8 (Promosi/Rollback)** — sama, waspada pencemaran baseline kalau ada validasi skala kecil sebelum verifikasi promosi skala besar.
- **Milestone 3.x (Real-time API)** — WAJIB baca KT-5 sebelum mendesain SLA/kontrak latensi, dan KT-6 sebelum menilai apakah `write_predictions` M2.5 perlu diubah. Juga WAJIB baca temuan konflik dokumen (real-time API tidak akan membaca feature store — `mlops-03-deployment-observability.md` baris 63 stale terhadap M2.2).
