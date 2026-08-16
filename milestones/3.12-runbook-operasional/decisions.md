# Keputusan — Milestone 3.12: Runbook Operasional

> **Catatan status**: file ini ditulis di **Checkpoint 1**, sebelum implementasi dimulai (pola konsisten sejak M3.11). **Living document** — diperbarui Checkpoint 7 dengan ringkasan hasil audit 4 simulasi terkontrol.

## Konteks Singkat

`docs/02-implementation-plan/mlops-03-deployment-observability.md` baris 247-263, dasar `docs/01-architecture/rancangan-arsitektur-mlops-platform.md` Bagian 8.2. **Milestone TERAKHIR di seluruh proyek** — satu dokumen operasional ringkas (runbook) yang merangkum skenario kegagalan yang sudah dibangun+diuji sepanjang M2.4-M3.11, sebagai satu rujukan tunggal saat insiden nyata terjadi, bukan dokumen arsitektur baru.

---

## Keputusan #1 — Lokasi Runbook: `docs/07-runbook-operasional/runbook-operasional.md`

**Keputusan final:** Runbook ditempatkan di `docs/07-runbook-operasional/runbook-operasional.md`, mengikuti pola numbered-docs existing (`docs/01-architecture` s.d. `docs/06-realtime-api-contract`) yang sudah established untuk dokumen "sumber kebenaran"/referensi lintas-milestone.

**Alasan:** Runbook secara definisi adalah dokumen referensi hidup yang dipakai lintas waktu saat insiden nyata terjadi — sifatnya sama dengan dokumen numbered-docs lain (kontrak skema, kontrak registry, kontrak API real-time), bukan artefak riwayat proses satu milestone.

**Tidak ada alternatif dipertimbangkan** — forced by pola established kuat proyek ini (6 numbered-docs folder sudah ada dengan fungsi serupa), tidak ada trade-off nyata untuk dieksplorasi.

---

## Keputusan #2 — Format: Satu File Markdown Terstruktur per Skenario

**Keputusan final:** Runbook berupa satu file Markdown, heading per skenario (6 entri), langkah bernomor per entri, tabel navigasi cepat di awal.

**Alasan:** Forced oleh teks sumber sendiri — eksplisit menyebut "satu dokumen operasional ringkas", bukan banyak dokumen terpisah.

**Tidak ada alternatif dipertimbangkan** — literal dari teks sumber.

---

## Keputusan #3 — Dokumen Rancangan Simulasi Terpisah: `rancangan-simulasi.md`

**Keputusan final:** Ekspektasi hasil terukur untuk tiap simulasi ditulis SEBELUM eksekusi di `milestones/3.12-runbook-operasional/rancangan-simulasi.md` — satu file living document, 4 section (satu per simulasi), tiap section ditulis tepat sebelum checkpoint eksekusinya, lalu diberi anotasi hasil audit setelahnya.

**Alasan:** Instruksi eksplisit user — mencegah rasionalisasi hasil setelah fakta (post-hoc): ekspektasi dikunci dulu secara tertulis, baru dibandingkan dengan hasil aktual. Ditempatkan di folder milestone (bukan `docs/07-...`) karena sifatnya riwayat proses verifikasi MILESTONE INI, bukan referensi operasional jangka panjang seperti runbook itu sendiri.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Tulis ekspektasi langsung di `logs.md` tanpa file terpisah** — ditolak: `logs.md` biasanya ditulis SETELAH/SELAMA eksekusi (naratif kronologis), bukan tempat alami untuk komitmen tertulis SEBELUM eksekusi — memisahkan file membuat urutan "rancangan dulu, baru eksekusi" lebih eksplisit dan tidak bisa diam-diam ditulis mundur (backdated).

---

## Keputusan #4 — "Siapa yang Perlu Tahu" = Operator/Pemilik Sistem (User)

**Keputusan final:** Tiap entri runbook menyatakan "siapa perlu tahu" sebagai operator/pemilik sistem tunggal (user), bukan struktur tim.

**Alasan:** Proyek solo — user berperan berbagai posisi (pola sama M3.7, user eksplisit mengonfirmasi berperan "tim DS" untuk notifikasi retraining). Tidak ada tim terpisah nyata untuk dirujuk.

**Tidak ada alternatif dipertimbangkan** — forced oleh realitas struktur proyek, konsisten preseden M3.7.

---

## Keputusan #5 — Entri "Dashboard/API Publik Bermasalah" Ditandai Pedigree Pengujian Lebih Tipis

**Keputusan final:** Entri ke-6 runbook (dashboard/API publik) DITULIS (Output wajib teks sumber), TAPI TIDAK mendapat simulasi terkontrol baru di KK2 — ditandai eksplisit di dalam runbook bahwa cakupan pengujiannya lebih tipis dibanding 4 skenario lain.

**Alasan:** M3.10 sudah menguji rate-limit (KK4) dan credential scope (KK2) secara nyata, tapi belum ada drill "API publik/dashboard benar-benar down" secara spesifik. KK1 M3.12 sendiri (parenthetical) hanya eksplisit menyebut "(drift, DAG gagal, API down, rollback)" — tidak menyebut dashboard/API publik dalam daftar itu, meski Output tetap memintanya sebagai isi runbook.

**Tidak ada alternatif dipertimbangkan untuk keputusan menulis-tapi-tidak-simulasi-baru** — ini pembacaan literal celah antara Lingkup (minta entri) dan KK1 (tidak mewajibkan bukti "sudah diuji" untuk skenario ini) — didokumentasikan jujur, bukan diklaim setara skenario lain.

---

## Keputusan #6 — Cakupan KK2: Simulasi SEMUA 4 Skenario (Keputusan User)

**Keputusan final:** KK2 diuji lewat SEMUA 4 skenario yang punya precedent teknik aman+reversibel (gerbang kualitas data stop, rollback model, real-time API down/lambat, drift terdeteksi) — bukan cuma 1 skenario minimum sesuai literal teks sumber ("uji coba terkontrol, salah satu skenario di atas").

**Alasan (dari user):** Closing milestone proyek — nilai verifikasi lebih menyeluruh dianggap lebih penting daripada minimalisme literal teks sumber, mengingat keempat teknik sudah tervalidasi aman di milestone-milestone sebelumnya (M3.8, M2.8/M3.4, M3.2/3.3/3.4/3.11, M3.6/3.7) — risiko inkremental menguji ke-4 dianggap kecil.

**Opsi yang Dipertimbangkan tapi Ditolak:**
- **Uji 1 skenario saja (Gerbang Kualitas Data Stop, REKOMENDASI saya)** — sesuai minimum literal teks sumber ("salah satu skenario di atas"), lebih cepat/rendah risiko operasional kumulatif. **Ditolak user** — ingin cakupan lebih menyeluruh untuk menutup proyek.

---

## Hasil Audit 4 Simulasi

Detail lengkap per butir ekspektasi ada di `rancangan-simulasi.md`. Ringkasan:

| Simulasi | Hasil Audit | Deviasi Ditemukan | Perbaikan Runbook |
|---|---|---|---|
| 1. Gerbang Kualitas Data Stop | 4/5 MATCH, 1 MATCH dengan deviasi kecil | Runbook tidak menyebut env var koneksi | Tambah `QUALITY_GATE_DB_URL` di entri 2b |
| 2. Rollback Model | 4/4 MATCH sempurna | Nol deviasi | Nol perbaikan diperlukan |
| 3. Real-Time API Down/Lambat | 2/5 MATCH penuh, 1 MATCH sebagian, 2 deviasi signifikan | (a) `healthz` JUGA gagal untuk host gagal-resolve-DNS-total (beda dari pola M3.2 unreachable-tapi-valid); (b) `curl` ke Service tidak representatif untuk diagnosis pod spesifik saat multi-replica | Tambah pembedaan 2 pola kegagalan config + instruksi `kubectl port-forward` untuk diagnosis pod spesifik |
| 4. Drift Terdeteksi | 5/6 MATCH (1 dengan insiden metodologi diperbaiki di tengah jalan, 1 dengan temuan tambahan), 1 deviasi kecil | (a) fitur override awal (`tenure`) ternyata SUDAH stop kronis sejak sebelum simulasi — diganti `tc_residual` di tengah eksekusi untuk transisi sebab-akibat bersih; (b) payload webhook berisi array `alerts[]` multi-fitur (grouped); (c) env var koneksi tidak disebutkan | Tambah `DRIFT_READER_DB_URL` + peringatan payload multi-fitur di entri 1 |

**Insiden operasional tambahan (di luar runbook, dicatat transparan):** HPA (M3.11, masih aktif) sempat scale-up ke 3 replica akibat noise CPU tidak terkait simulasi manapun di M3.12 — pada Simulasi 3, ini menyebabkan kontensi memori node (pod baru `Pending`, `Insufficient memory`) yang diatasi dengan `kubectl scale --replicas=1` sementara. Tidak mengubah kesimpulan audit KK2 (root cause tetap teridentifikasi dan diverifikasi benar), tapi dicatat sebagai kondisi lingkungan nyata yang harus ditangani di tengah eksekusi — konsisten pola "tidak menyembunyikan insiden" seluruh proyek ini.

**Kesimpulan keseluruhan KK2:** Keempat simulasi BERHASIL — bukan karena semuanya berjalan mulus tanpa temuan (2 dari 4 justru menemukan gap signifikan), tapi karena metodologi rancangan→eksekusi→ikuti-runbook→audit BEKERJA SEPERTI DIRANCANG: ekspektasi yang dikunci sebelum eksekusi memberi dasar objektif untuk mendeteksi deviasi (termasuk deviasi dari asumsi SAYA sendiri saat menulis rancangan, seperti kasus `tenure` yang ternyata sudah stop kronis) — bukan rasionalisasi hasil setelah fakta. 6 dari total ~10 gap/temuan yang terungkap LANGSUNG diperbaiki di runbook operasional, bukan cuma dicatat sebagai catatan kaki.
