# Report — Milestone 3.4: Deteksi Versi Model Aktif Tanpa Restart Penuh

## Ringkasan

Milestone 3.4 SELESAI — real-time API sekarang mendeteksi perubahan alias `champion` di MLflow registry secara berkala (polling `asyncio`, 30 detik) dan reload model TANPA restart/redeploy manual, menuntaskan keterbatasan yang sengaja diterima sejak M3.2.

**Temuan terpenting milestone ini bukan mekanisme polling itu sendiri (yang berhasil sesuai desain sejak awal), tapi bug produksi besar yang ditemukan saat verifikasinya**: manifest `MLmodel` yang diregistrasi dari mesin dev Windows menyimpan path artifact dengan backslash literal pada field yang SALAH — bug ini TIDAK PERNAH benar-benar tertutup sejak mitigasi Milestone 2.5 (mitigasi itu menyasar variabel yang salah). Root cause di-trace sampai ke baris kode INTERNAL MLflow sendiri (`mlflow/pyfunc/model.py`, `os.path.join()` native Windows), dibuktikan lewat perbandingan manifest byte-per-byte dan investigasi bertahap yang membantah 4 hipotesis lain terlebih dahulu. Fix diterapkan di `registry.py` (post-process manifest S3), diverifikasi bekerja, dan TIDAK menimbulkan regresi (201/201 test).

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Simulasi promosi versi baru di registry... diikuti oleh service ini mulai menghasilkan prediksi dari versi baru dalam rentang waktu yang wajar, tanpa restart/redeploy manual." | `scripts/promote_active_alias.py 5 champion` (registry produksi sungguhan) — `/readyz` berubah `"1"`→`"5"` dalam ~42 detik (interval polling 30s + waktu reload), pod K8s SAMA (`churn-api-6bc9d7f57-q7hn5`), `RESTARTS: 0` sepanjang proses. |
| **KK2** | "Simulasi rollback... menghasilkan service kembali memakai versi sebelumnya dengan kecepatan yang sesuai ekspektasi 'rollback cepat'." | `promote_active_alias.py 1 champion` — `/readyz` kembali `"5"`→`"1"` dalam ~10 detik, pod TETAP SAMA, `RESTARTS: 0` di SELURUH siklus promosi+rollback gabungan. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 5 keputusan desain awal (polling forced, state immutable forced by race condition, satu fungsi refresh, interval 30s, `asyncio.to_thread` forced) + 1 bug besar ditemukan+diperbaiki (Keputusan #6, root-cause+fix+verifikasi lengkap, termasuk investigasi bertahap yang membantah beberapa hipotesis salah sebelum menemukan akar masalah sebenarnya).

## Perubahan dari Plan Awal

**Penyimpangan signifikan**: Checkpoint 2 (verifikasi KK1/KK2) awalnya diperkirakan langsung sukses (mekanisme sudah teruji lewat 4 unit test Checkpoint 1). Percobaan pertama verifikasi GAGAL total (versi tidak pernah berubah meski dipromosikan) — memicu investigasi mendalam ~2 jam yang MEMBANTAH beberapa hipotesis (caching koneksi database, masalah jaringan container, bug logika `_refresh_once`) sebelum menemukan akar masalah SEBENARNYA (bug artifact path MLflow, sama sekali di luar scope kode M3.4 sendiri). Fix diterapkan LANGSUNG (bukan ditunda) karena: (a) memblokir verifikasi KK1/KK2 sepenuhnya (tidak ada kandidat versi lain yang bisa dimuat untuk diuji); (b) bug ini akan mempengaruhi SETIAP promosi model di masa depan, bukan cuma masalah M3.4; (c) fix minimal dan tervalidasi regresi nol. Efek samping tak terduga lain: `kubectl exec` untuk debugging sempat OOM-kill pod produksi (resource limit M3.3), memicu 1 restart tidak disengaja — diselesaikan dengan mengulang verifikasi final dari baseline bersih dan beralih ke container Linux terpisah (`docker run`) untuk kebutuhan debugging berikutnya.

## Keterbatasan dan Item Terbuka

- **Interval polling 30 detik adalah default, bukan SLA formal** — KT-5 (`docs/keputusan-tertunda.md`, verdict latensi real-time API) tetap belum ditutup, tidak berubah oleh milestone ini.
- **Versi 2, 3, 4 (artifact rusak, hasil debugging sesi ini) tetap ada di registry, tidak beralias** — tidak berbahaya (tidak ada konsumen yang mereferensikannya), tapi menambah clutter historis. Tidak dihapus (MLflow model version deletion adalah operasi destruktif, di luar cakupan milestone ini untuk versi yang sudah tidak relevan).
- **Bug artifact path (Keputusan #6) hanya diverifikasi untuk SATU skenario registrasi** (bundle preprocessor+model dari `build_bundle()`) — belum ada test permanen yang khusus menguji `_fix_windows_artifact_paths()` sebagai unit terisolasi (verifikasi sejauh ini end-to-end: registrasi asli → load dari container Linux terpisah).
- **`kubectl exec` untuk debugging DI DALAM pod produksi terbukti berisiko** (OOM dengan resource limit M3.3 yang ketat, 768Mi) — bukan masalah baru yang perlu diperbaiki di M3.4, tapi catatan operasional: kebutuhan debugging serupa di masa depan sebaiknya pakai container terpisah (`docker run`), bukan `kubectl exec` di pod produksi yang resource-nya sudah pas-pasan.
- **Belum ada test regresi permanen untuk mekanisme refresh berjalan di K8s sungguhan** — verifikasi KK1/KK2 dilakukan manual/interaktif (`promote_active_alias.py` + polling `curl`), konsisten pola M3.1-3.3, bukan diotomasi sebagai test CI.

## Follow-up

- Pertimbangkan menambah test permanen untuk `_fix_windows_artifact_paths()` (mis. mock S3/artifact_uri, verifikasi normalisasi path) — kandidat kuat untuk sesi berikutnya, mengingat bug yang diperbaikinya cukup serius (mempengaruhi SETIAP registrasi model dari Windows).
- M3.5 (Monitoring): metrik "waktu deteksi versi baru" (selisih waktu promosi vs pickup) bisa jadi kandidat metrik operasional yang relevan dipantau, mengingat sudah ada bukti pengukuran nyata dari milestone ini.
- Pembersihan versi model registry yang tidak relevan (2, 3, 4) bisa dilakukan kapan saja tanpa risiko — tidak mendesak.
- Evaluasi ulang apakah mitigasi serupa (`_fix_windows_artifact_paths()`) perlu diterapkan di titik registrasi model LAIN kalau ada di masa depan (saat ini hanya `register_model()` yang jadi satu-satunya jalur registrasi resmi, sudah tercakup).
