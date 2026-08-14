# Report — Milestone 3.6: Monitoring Drift dan Kualitas Model

## Ringkasan

Milestone 3.6 SELESAI — distribusi 29 fitur input model + output prediksi (`churn_probability`) sekarang dipantau dua tingkat (PSI + KS-test/Chi-square) membandingkan baseline data training (`telco_customers_source`, 594.194 baris, byte-identik terverifikasi `notebook-audit.md` Bagian H.2) terhadap data produksi sintetis terbaru (`telco_customers_synthetic`). Hasil tersaji di dashboard Grafana yang SAMA dengan M3.5 (bukan dashboard baru), lewat exporter lean K8s baru yang murni membaca hasil pra-komputasi — komputasi statistik berat (butuh model+scipy) berjalan event-driven di GitHub Actions, dipicu otomatis setiap kali data sintetis baru selesai discor (M2.9), tanpa mengubah satu baris pun kode pipeline batch Orang #2.

Metodologi dua-tingkat adalah ide user sendiri (bukan usulan sepihak) — dipilih setelah diskusi mendalam dengan contoh numerik dari data proyek, dan terbukti bernilai nyata: run pertama terhadap data produksi sungguhan langsung menemukan pola "signifikan secara statistik, tidak signifikan secara praktis" (p-value ekstrem rendah tapi PSI rendah) pada 2 fitur — persis skenario yang jadi alasan memilih dua tingkat sejak awal.

## Kriteria Keberhasilan vs Bukti

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | "Pergeseran distribusi fitur buatan (uji coba terkontrol) berhasil terdeteksi dan memicu sinyal yang terlihat di dashboard." | Override JSON (2 fitur digeser ekstrem jauh dari baseline) dijalankan lewat `compute_drift.py --override-current` — PSI melonjak dari ~0/0.014 (pass) jadi **7.68/8.28** (>> ambang stop 0.25), verdict "stop". Panel dashboard "Jumlah Fitur Verdict STOP" (query lewat jalur proxy Grafana yang sama persis dipakai panel) naik dari **2 jadi 4**. Data direstore setelahnya, dikonfirmasi kembali ke nilai asli. |
| **KK2** | "Ambang batas yang dipakai terdokumentasi beserta alasan pemilihannya bersama Orang #1 — bukan angka default yang tidak dipahami asal-usulnya." | `decisions.md` Keputusan #9: PSI (<0.1/0.1-0.25/≥0.25, konvensi industri credit-scoring/MLOps lama dipakai luas) dan p-value (≥0.05/0.01-0.05/<0.01, konvensi signifikansi statistik α standar) — keduanya bukan angka dikarang, dan dipilih user sendiri lewat `AskUserQuestion` setelah penjelasan trade-off detail (2 putaran diskusi). |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 2 keputusan genuinely terbuka via `AskUserQuestion` (metodologi dua-tingkat PSI+KS/Chi2 milik ide user sendiri; cakupan jalur batch-saja), 9 keputusan turunan dari preseden proyek (M2.1/M2.4/M2.5/M2.9/M3.4/M3.5), dan 1 kendala teknis ditemukan+dipecahkan (`registry.load_active_pipeline()`, akses `PreprocessingPipeline` fitted tanpa API publik).

## Perubahan dari Plan Awal

Tidak ada penyimpangan besar — seluruh 5 checkpoint (fondasi matematis → baseline → current-window+trigger → exporter+K8s → dashboard+verifikasi) berjalan sesuai urutan rencana. Penyesuaian proses kecil: workflow `.github/workflows/drift-monitoring.yml` (Task 9) di-commit+push LEBIH AWAL dari batas checkpoint biasa (sebelum Task 10 selesai) — satu-satunya cara memverifikasi `workflow_dispatch` secara nyata (mensyaratkan file ada di branch default GitHub). Bukan pelanggaran disiplin commit-per-checkpoint, murni kebutuhan teknis verifikasi.

Dua insiden operasional (bukan bug kode) ditemukan+diselesaikan di tempat: Docker Desktop mati saat mulai build image (Checkpoint 4, di-restart via PowerShell), dan percobaan pertama restore data pasca-uji-coba-terkontrol timeout (Checkpoint 5, percobaan kedua sukses). Keduanya dicatat lengkap di `logs.md`.

## Keterbatasan dan Item Terbuka

- **Cakupan real-time API sengaja TIDAK dibangun** — KT-9 (`docs/keputusan-tertunda.md`) baru, konsisten pola KT-5/7/8. Real-time API belum punya pemanggil eksternal nyata; trafik yang ada murni verifikasi manual, tidak representatif untuk drift monitoring bermakna.
- **Baseline output prediksi (`churn_probability`) tied ke versi model AKTIF saat baseline dihitung** — kalau `champion` berganti versi (M2.8) SETELAH baseline dihitung, perbandingan drift output selanjutnya confounded (campur "perubahan data" dengan "perubahan model"). Tidak ada mekanisme re-trigger baseline otomatis saat alias berganti — dicatat sebagai follow-up, bukan diselesaikan sekarang.
- **Sample `telco_customers_synthetic` saat ini cuma 1.000 baris dari SATU batch generasi** (bukan aliran berkelanjutan near-real-time) — PSI/KS-test atas sample sekecil ini valid secara matematis tapi representativitasnya terhadap "drift produksi jangka panjang" masih terbatas. Akan membaik begitu generator dijalankan lebih sering (di luar kendali M3.6).
- **`registry.load_active_pipeline()` bergantung struktur internal MLflow** (`_model_impl.python_model`, bukan API publik terdokumentasi) — titik rapuh dicatat eksplisit di docstring, perlu dicek ulang kalau `mlflow-skinny` di-upgrade dari `3.15.1`.
- **Verifikasi visual browser pasca-uji-coba-terkontrol tidak berupa screenshot penuh** — rendering panel Grafana tidak konsisten di sesi ini (lihat `logs.md` Checkpoint 5 untuk detail). Bukti utama dipakai lewat query API Grafana datasource-proxy (jalur PERSIS sama dipakai panel), dikombinasikan dengan capture browser SEBELUM override yang berhasil menunjukkan seluruh 9 panel M3.5 bekerja normal.
- **Tidak ada alerting/notifikasi eksternal** — di luar cakupan M3.6 (KK2 minta "sinyal terlihat di dashboard", bukan "dikirim ke kanal notifikasi" — itu tugas M3.7 eksplisit).

## Follow-up

- M3.7 (notifikasi retraining): threshold+verdict yang sudah ada di `drift.drift_check_results` bisa langsung jadi trigger notifikasi — tidak perlu mekanisme deteksi baru, tinggal tambah jalur kirim.
- M3.8 (dashboard+alerting terpadu): panel M3.6 sudah ada di dashboard yang sama sejak awal — tinggal rapikan tata letak+tambah alerting rule di atas panel yang sudah ada.
- Pertimbangkan mekanisme re-trigger `compute_drift.py --mode baseline` otomatis saat alias `champion` berganti versi (M2.8) — menutup keterbatasan baseline-output-stale di atas.
- Evaluasi ulang KT-9 begitu real-time API punya pemanggil eksternal nyata — arsitektur `compute_drift.py`/`drift_exporter.py` sudah generik (baca dari tabel manapun), perluasan ke jalur real-time relatif kecil kalau saatnya tiba (perlu persistence baru di `app.py` dulu, itu bagian yang belum ada).
