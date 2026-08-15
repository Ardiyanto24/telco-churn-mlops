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

`[DIISI CHECKPOINT 7]` — akan berisi ringkasan MATCH/DEVIASI tiap simulasi (rujuk `rancangan-simulasi.md` untuk detail lengkap per butir ekspektasi) dan daftar perbaikan runbook yang ditemukan selama uji coba (kalau ada).
