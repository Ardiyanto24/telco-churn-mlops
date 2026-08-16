# Report — Milestone 3.12: Runbook Operasional

## Ringkasan

Milestone 3.12 SELESAI — **milestone TERAKHIR di seluruh proyek MLOps ini**. Satu dokumen operasional (`docs/07-runbook-operasional/runbook-operasional.md`) merangkum 6 skenario kegagalan (drift terdeteksi; DAG batch gagal/gerbang kualitas data stop dua sub-kasus; real-time API down/lambat; rollback versi model; rollback deployment K8s; dashboard/API publik bermasalah), masing-masing format konsisten Gejala→Diagnosis→Langkah Respons→Verifikasi Selesai→Rujukan.

Sesuai keputusan user (berbeda dari rekomendasi awal saya yang menyarankan 1 skenario minimum), KK2 diverifikasi lewat **4 simulasi terkontrol komprehensif** — masing-masing mengikuti metodologi ketat rancangan→eksekusi→ikuti-runbook-persis→audit (instruksi eksplisit user: ekspektasi dikunci SEBELUM eksekusi, dibandingkan dengan hasil aktual SETELAHNYA, mencegah rasionalisasi post-hoc). Metodologi ini terbukti bernilai nyata: **2 dari 4 simulasi menemukan deviasi signifikan** dari asumsi awal — termasuk satu insiden metodologi yang ditemukan dan diperbaiki DI TENGAH eksekusi (Simulasi 4).

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Untuk setiap skenario kegagalan utama yang sudah diuji coba terkontrol di milestone sebelumnya (drift, DAG gagal, API down, rollback), ada entri runbook yang jelas dan bisa diikuti tanpa perlu membuka ulang seluruh dokumen rancangan." | 6 entri ditulis (`docs/07-runbook-operasional/runbook-operasional.md`), format konsisten, tabel navigasi cepat berbasis gejala. 4 dari 6 entri (drift, DAG gagal, API down, rollback model+deployment — TIDAK termasuk dashboard/API publik, lihat Keterbatasan) DIVERIFIKASI NYATA lewat simulasi terkontrol M3.12 sendiri (bukan cuma diklaim benar di atas kertas) — lihat KK2. |
| **KK2** | "Simulasi insiden baru (uji coba terkontrol, salah satu skenario di atas) berhasil ditangani mengikuti langkah di runbook, tanpa perlu improvisasi besar di luar apa yang tertulis." | **4 simulasi lengkap** (bukan 1, keputusan user): (1) Gerbang kualitas data stop — 4/5 MATCH sempurna; (2) Rollback model — 4/4 MATCH sempurna, nol deviasi; (3) Real-time API down/lambat — 2/5 MATCH penuh + 2 deviasi signifikan ditemukan+diperbaiki; (4) Drift terdeteksi — 5/6 MATCH + 1 deviasi kecil, TERMASUK insiden metodologi (fitur override awal ternyata sudah drift kronis) yang ditemukan+diperbaiki di tengah eksekusi. Total **6 perbaikan runbook** dilakukan langsung berdasar temuan audit nyata, bukan spekulasi. Detail lengkap tiap butir ekspektasi: `rancangan-simulasi.md`. |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 6 keputusan desain (lokasi runbook `docs/07-...`, format satu file, `rancangan-simulasi.md` terpisah untuk audit pra-registrasi, siapa perlu tahu = operator tunggal, pedigree dashboard/API publik lebih tipis) + keputusan user cakupan KK2 (4 skenario komprehensif, berbeda dari rekomendasi saya) + ringkasan hasil audit 4 simulasi.

## Perubahan dari Plan Awal

1. **Cakupan KK2 diperluas dari 1 skenario (rekomendasi saya) jadi 4 skenario** (keputusan user) — perubahan signifikan tapi sudah disepakati sebelum plan final ditulis, bukan penyimpangan di tengah jalan.
2. **Metodologi rancangan→eksekusi→audit** ditambahkan atas instruksi eksplisit user terhadap draf plan awal — bukan bagian breakdown awal saya, tapi koreksi proses SEBELUM implementasi dimulai (lihat riwayat plan mode sesi ini).
3. **Insiden metodologi Simulasi 4 (di tengah eksekusi, bukan direncanakan)**: fitur override awal (`tenure`) ternyata sudah drift kronis dari data produksi asli sejak sebelum simulasi — terdeteksi LEWAT proses audit itu sendiri, diperbaiki dengan mengganti fitur (`tc_residual`) tanpa menyimpang dari metodologi (rancangan tetap ditulis ulang untuk fitur baru sebelum lanjut, bukan diakali).
4. **Insiden operasional Simulasi 3 (tidak direncanakan)**: HPA (M3.11, masih aktif) menyebabkan kontensi memori node (pod baru `Pending`) di tengah simulasi — diatasi `kubectl scale --replicas=1` sementara, tidak mengubah kesimpulan audit.

## Keterbatasan dan Item Terbuka

- **Entri "Dashboard/API Publik Bermasalah" TIDAK mendapat simulasi terkontrol baru** — ditandai eksplisit di dalam runbook sendiri (Keputusan Desain #5) sebagai entri dengan pedigree pengujian lebih tipis, berbasis mekanisme M3.10 (kredensial+rate-limit) yang sudah teruji TAPI belum ada drill "down" spesifik. KK1 sendiri (parenthetical teks sumber) tidak eksplisit mewajibkan skenario ini diuji — dibaca dan didokumentasikan jujur, bukan diklaim setara 5 entri lain.
- **Simulasi 2 (Rollback Model) tidak menguji ulang independen refresh loop real-time API ~30-42 detik** — window promosi ke versi 5 diminimalkan demi keamanan operasional produksi, bersandar verifikasi M3.4 sebelumnya untuk klaim timing tersebut.
- **6 perbaikan runbook** yang ditemukan lewat audit SUDAH diterapkan langsung ke `docs/07-runbook-operasional/runbook-operasional.md` — tapi ini TIDAK menjamin runbook 100% lengkap untuk skenario yang belum pernah teruji sama sekali (mis. kombinasi kegagalan berlapis, insiden di luar 6 kategori yang dicakup).
- **HPA M3.11 tetap aktif** dan bisa menyebabkan kontensi resource serupa Simulasi 3 di masa depan kalau operasi manual (mis. debugging manual, `kubectl exec`) kebetulan bertepatan dengan scale-up — bukan bug baru, konsekuensi karakteristik KD-3 yang sudah didokumentasikan M3.11.

## Follow-up

- **Tidak ada follow-up milestone lanjutan** — ini titik akhir seluruh rangkaian proyek (`Catatan Serah Terima`, dokumen implementasi M3.x). Follow-up yang tersisa murni operasional/reaktif: kalibrasi ulang begitu ada trafik produksi nyata (KT-5/7/8/9/12), evaluasi ulang keputusan tertunda lain begitu pemicunya terjadi (`docs/keputusan-tertunda.md`, 12 entri terbuka), retensi `monitoring.metrics_snapshot` (KT-11) begitu volume jadi masalah nyata.
- Runbook (`docs/07-runbook-operasional/runbook-operasional.md`) adalah dokumen HIDUP — perbaiki lagi begitu insiden nyata (bukan simulasi) menemukan gap baru, konsisten pola audit yang sudah terbukti bernilai di milestone ini.
