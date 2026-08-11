# Rancangan Implementasi — Pipeline & Orchestration

**MLOps Platform — Telekomunikasi (Churn/Risk Prediction)**

| | |
|---|---|
| **Pemilik pekerjaan** | 1 orang (ML Engineer — Pipeline & Orchestration) |
| **Dokumen induk** | `rancangan-arsitektur-mlops-platform.md` (Bagian 2, 3.2, 3.4, 5, 6.1, 6.3) |
| **Cakupan pekerjaan** | Modul transformasi & inference service package (dari `mlops-01-productionization.md`) → batch scoring DAG terjadwal → feature store ter-refresh → hasil tertulis ke PostgreSQL → CI/CD → model teregistrasi dan terkelola versinya di MLflow |
| **Tidak termasuk** | Membangun modul transformasi/preprocessing itu sendiri (sudah selesai — lihat `mlops-01-productionization.md`, dikonsumsi di sini sebagai dependency); real-time inference API, deployment ke Kubernetes, dan observability (lihat `mlops-03-deployment-observability.md`) |
| **Status dokumen** | Rancangan implementasi kerja — bukan dokumen arsitektur |

---

## Cara Membaca Dokumen Ini

Sama seperti dokumen Orang #1: berisi **milestone**, bukan task list atomic. Tiap milestone punya lingkup, alasan kenapa dipisah, output, dan kriteria keberhasilan yang bisa diverifikasi. Urutan di bawah adalah urutan yang disarankan (mengikuti dependency data dan infrastruktur), bukan urutan kaku — temuan di satu milestone, misalnya volume data yang ternyata lebih besar dari perkiraan atau frekuensi refresh yang ternyata perlu lebih sering, wajar mengubah detail milestone sesudahnya.

Rujukan wajib: `rancangan-arsitektur-mlops-platform.md` Bagian 2 (prinsip mengikat, terutama soal feature store precomputed dan rollback via registry), Bagian 5 (siklus hidup model), dan Bagian 6.3 (isolasi beban database) — dokumen ini tidak mengutip ulang isinya secara detail, hanya merujuk saat relevan.

---

## Konteks dan Prinsip Kunci yang Perlu Dipegang

Beberapa keputusan dari dokumen arsitektur sudah final dan **membatasi** bagaimana pekerjaan ini dilakukan:

- **Pekerjaan ini memakai, bukan membangun ulang, logika transformasi.** Setiap langkah di DAG yang menyentuh preprocessing atau feature engineering wajib memanggil package dari Orang #1 (Milestone 1.5 di `mlops-01-productionization.md`) — bukan menulis ulang logika serupa secara terpisah, sekecil apa pun alasannya (mis. "biar lebih cepat di orchestrator"). Pelanggaran prinsip ini adalah penyebab paling mungkin dari *batch-realtime skew* yang disebut eksplisit sebagai risiko di dokumen arsitektur.
- **Feature store adalah komponen bersama, bukan milik batch semata.** Meski pekerjaan me-refresh-nya ada di sini, feature store dibaca dengan frekuensi tinggi oleh real-time API (Orang #3). Refresh yang mengganggu baca (data setengah-refresh, downtime baca) melanggar prinsip eksplisit di Bagian 2 dokumen arsitektur — desain refresh harus sadar akan konsumen keduanya sejak awal, bukan didesain seolah feature store hanya dipakai internal.
- **Rollback model berarti mengganti penanda versi aktif di registry, bukan redeploy.** Konsekuensinya, mekanisme promosi versi yang dirancang di sini harus membuat perubahan versi aktif itu sendiri **cukup** untuk memengaruhi kedua jalur (batch dan real-time) — bukan memerlukan langkah tambahan di masing-masing sisi setiap kali versi berganti.
- **CI/CD di sini punya tiga gerbang wajib** (Bagian 6.1 dokumen arsitektur): unit test modul transformasi (dari Orang #1), verifikasi parity batch-vs-realtime, dan test sebelum deployment service (bagian Orang #3, tapi pipeline CI yang menjalankannya adalah milik pekerjaan ini). Ketiganya harus benar-benar jadi gerbang yang menghentikan proses kalau gagal — bukan langkah yang dilewati kalau "kelihatannya baik-baik saja".
- **PostgreSQL dipakai bersama, bukan eksklusif.** Batch pipeline di sini melakukan baca berat (agregasi historis untuk feature store dan scoring) dan tulis (hasil prediksi, feature store) ke database yang sama yang juga dibaca real-time API dengan kebutuhan latensi rendah. Desain jadwal dan strategi refresh perlu sadar akan ini sejak awal (Bagian 6.3 dokumen arsitektur), bukan ditemukan sebagai masalah performa setelah keduanya berjalan bersamaan.
- **Setiap hasil prediksi wajib bisa ditelusuri asalnya.** Tabel hasil batch (Milestone 2.5) wajib menyimpan versi model dan snapshot/waktu data yang dipakai — ini prasyarat lineage yang dinyatakan mengikat di Bagian 5.6 dokumen arsitektur, bukan kolom opsional yang bisa ditambahkan belakangan kalau sempat.
- **Data yang masuk pipeline perlu lolos pemeriksaan kewajaran, bukan hanya kelengkapan skema.** Validasi skema (Milestone 1.3 Orang #1) memeriksa *bentuk* data. Pekerjaan ini menambahkan gerbang terpisah yang memeriksa *kewajaran* data harian dibanding pola historisnya sendiri — dua hal yang berbeda dan keduanya wajib ada (Bagian 6.1 dokumen arsitektur).

---

## Milestone 2.1 — Fondasi Orchestrator dan Model Registry

### Lingkup
Men-setup platform orchestrator yang akan menjalankan seluruh job terjadwal di pekerjaan ini (feature store refresh, batch scoring DAG), serta menyiapkan MLflow sebagai model registry — termasuk konvensi penamaan run/versi model, dan menyepakati definisi konkret "versi aktif" yang akan dipakai baik batch DAG di sini maupun real-time API (Orang #3) untuk menentukan model mana yang dipanggil.

### Kenapa Ini Jadi Milestone Terpisah
Ini prasyarat infrastruktur murni yang harus ada sebelum milestone lain di dokumen ini bisa berjalan terjadwal — dipisah secara eksplisit dari milestone berikutnya (yang fokus ke logic pipeline) agar keputusan platform (tool orchestrator apa, bagaimana konvensi versi model) tidak tercampur dengan keputusan konten pipeline itu sendiri. Konvensi "versi aktif" di MLflow perlu disepakati di titik ini karena Orang #3 bergantung pada definisi yang sama untuk merancang mekanisme deteksi versi aktif di real-time API (lihat Bagian 5.2 dokumen arsitektur).

### Output
- Platform orchestrator terpasang dan bisa menjalankan job terjadwal.
- MLflow model registry terpasang, dengan model dari Orang #1 sudah teregistrasi sebagai versi awal.
- Konvensi penamaan versi dan definisi teknis "versi aktif" (mis. tag/stage tertentu di MLflow) yang terdokumentasi sebagai acuan bersama.

### Kriteria Keberhasilan
- Job percobaan sederhana berhasil dijadwalkan dan dijalankan melalui platform orchestrator.
- Model dari Orang #1 berhasil diregistrasi ke MLflow dan dapat dimuat kembali (round-trip) menggunakan mekanisme pemuatan berbasis versi dari inference service package (Milestone 1.5 di `mlops-01-productionization.md`).
- Definisi "versi aktif" terdokumentasi dan dapat dipahami tanpa ambiguitas oleh pihak lain (diverifikasi dengan mengonfirmasi pemahaman ke Orang #3).

---

## Milestone 2.2 — Klasifikasi Fitur ke Desain Feature Store

### Lingkup
Menerjemahkan hasil klasifikasi fitur seketika vs historis dari Milestone 1.1 (`mlops-01-productionization.md`) menjadi desain konkret feature store: tabel apa saja yang dibutuhkan di PostgreSQL, kolom apa yang disimpan, granularitas per apa (mis. per subscriber), dan bagaimana nilai fitur historis ini dihitung dari data mentah — memakai logika perhitungan fitur yang sama persis dengan yang didefinisikan Orang #1, bukan reimplementasi.

### Kenapa Ini Jadi Milestone Terpisah
Ini titik penerjemahan dari "apa yang dibutuhkan model" (keputusan Orang #1) menjadi "bagaimana itu tersedia secara teknis" (keputusan infrastruktur) — memisahkannya memungkinkan desain skema feature store direview sebelum implementasi refresh job yang lebih mahal diubah setelah berjalan.

### Output
- Skema tabel feature store di PostgreSQL (nama tabel, kolom, tipe, granularitas, kolom metadata seperti waktu perhitungan terakhir).
- Pemetaan eksplisit: fitur historis dari Milestone 1.1 → kolom feature store yang mewakilinya, dengan logika perhitungan yang merujuk langsung ke definisi Orang #1 (bukan didefinisikan ulang di sini).

### Kriteria Keberhasilan
- Setiap fitur historis dari daftar Milestone 1.1 punya kolom yang jelas di skema feature store, tanpa ada fitur yang terlewat atau ambigu.
- Skema ini sudah dibagikan dan dikonfirmasi dipahami oleh Orang #3 (dikonsumsi sebagai sumber baca real-time API).

---

## Milestone 2.3 — Job Refresh Feature Store

### Lingkup
Membangun job terjadwal yang menghitung ulang nilai fitur historis dari data mentah PostgreSQL dan memperbarui feature store sesuai skema Milestone 2.2 — dengan mekanisme refresh yang menjamin real-time API tidak pernah membaca data setengah-refresh (mis. strategi refresh-lalu-swap, bukan update baris satu-per-satu yang bisa terbaca dalam kondisi tidak konsisten di tengah proses).

### Kenapa Ini Jadi Milestone Terpisah
Ini implementasi konkret dari prinsip "feature store aman dibaca kapan pun" yang dinyatakan eksplisit sebagai keputusan mengikat di Bagian 2 dokumen arsitektur — layak berdiri sebagai unit kerja tersendiri yang divalidasi ketat, mengingat kegagalan di sini berdampak langsung ke jalur real-time yang dipegang orang lain (Orang #3), bukan hanya ke pekerjaan sendiri.

### Output
- Job refresh feature store berjalan terjadwal, memakai logika perhitungan fitur dari Orang #1.
- Mekanisme refresh yang tidak mengganggu baca bersamaan (didokumentasikan strategi konkretnya — swap table atau setara).
- Baseline awal: berapa lama proses refresh berjalan dan seberapa sering perlu dijalankan (temuan ini menjadi masukan untuk Milestone 2.5 soal isolasi beban).

### Kriteria Keberhasilan
- Feature store berhasil ter-refresh terjadwal, dan nilai hasil refresh cocok dengan perhitungan manual/sampel untuk beberapa entity uji.
- Simulasi pembacaan feature store yang terjadi **persis saat** refresh sedang berlangsung (uji coba terkontrol) tidak menghasilkan data yang error, kosong, atau setengah-refresh.
- Refresh berikutnya (setelah data mentah berubah, uji coba terkontrol) menghasilkan nilai fitur yang ter-update sesuai perubahan tersebut — membuktikan job benar-benar menghitung ulang, bukan menyimpan nilai statis.

---

## Milestone 2.4 — Gerbang Kualitas Data Harian

### Lingkup
Membangun pemeriksaan kewajaran data mentah sebelum diproses lebih lanjut oleh batch scoring — volume baris hari ini dibanding baseline historis (rolling, bukan angka statis), proporsi nilai kosong pada kolom kritis yang biasanya lengkap, dan nilai pada kolom kunci bisnis yang berada di luar rentang wajar. Ini berbeda dari validasi skema (Milestone 1.3 Orang #1, yang memeriksa bentuk data) — gerbang ini memeriksa kewajaran nilai dan volume, independen dari apakah skemanya sudah benar.

### Kenapa Ini Jadi Milestone Terpisah
Dokumen arsitektur (Bagian 6.1) menyatakan ini sebagai gerbang CI/CD yang wajib ada, terpisah dari validasi skema maupun drift model — data bisa saja punya skema yang benar tapi nilainya sudah rusak di sumbernya (mis. sensor data generator bermasalah sesaat), dan tanpa gerbang ini, DAG batch (Milestone 2.5) bisa saja berhasil menghasilkan prediksi dari data yang sebenarnya sudah tidak wajar, tanpa terdeteksi sampai hasilnya terlihat aneh di dashboard jauh di hilir.

### Output
- Pemeriksaan volume baris harian dibanding baseline rolling, dengan ambang batas yang wajar (tidak terlalu sensitif, tidak terlalu tumpul).
- Pemeriksaan proporsi NULL pada kolom kritis dan pemeriksaan rentang nilai wajar pada kolom kunci bisnis.
- Mekanisme yang menghentikan/menandai run DAG saat data tidak lolos gerbang ini, alih-alih meneruskan data yang sudah tidak wajar ke scoring.

### Kriteria Keberhasilan
- Penyimpangan volume atau nilai buatan (uji coba terkontrol: menyuntik data uji dengan volume anjlok drastis atau proporsi NULL melonjak) berhasil terdeteksi dan menghentikan/menandai run sebelum data itu sampai ke scoring.
- Kondisi data normal (fluktuasi wajar sehari-hari) tidak memicu false alert — ambang batas cukup toleran terhadap variasi normal.

---

## Milestone 2.5 — Batch Scoring DAG

### Lingkup
Membangun pipeline batch scoring sebagai rangkaian task dengan dependency eksplisit: ambil data mentah dari PostgreSQL (dan feature store yang relevan) → lolos gerbang kualitas data (Milestone 2.4) → panggil transformasi & validasi (memakai package dari Orang #1) → jalankan prediksi memakai model versi aktif dari MLflow registry → tulis hasil prediksi balik ke PostgreSQL, termasuk kolom lineage (versi model dan snapshot/waktu data yang dipakai, sesuai Bagian 5.6 dokumen arsitektur). Termasuk penanganan kegagalan di tiap task — retry otomatis, alert, atau berhenti dengan aman tanpa merusak data yang mungkin sedang dipakai konsumen lain.

### Kenapa Ini Jadi Milestone Terpisah
Ini implementasi inti dari jalur batch — dipisah dari Milestone 2.3 (feature store) karena sifatnya berbeda: feature store adalah infrastruktur pendukung yang dipakai dua jalur, sementara DAG ini murni jalur batch itu sendiri. Baru bisa dikerjakan dengan baik setelah feature store, model registry (Milestone 2.1–2.3), dan gerbang kualitas data (Milestone 2.4) tersedia sebagai dependency-nya.

### Output
- DAG batch scoring berjalan terjadwal, dengan dependency antar task terdokumentasi eksplisit, termasuk gerbang kualitas data sebagai salah satu task.
- Mekanisme tulis hasil ke PostgreSQL yang reliable: skema tabel tujuan disepakati (termasuk kolom lineage — versi model, waktu/snapshot data), ada retry saat gagal, mekanisme upsert/insert yang tidak merusak data yang sedang dipakai sistem lain.
- Penanganan kegagalan per task (retry, alert, atau stop aman) terkonfigurasi dan terdokumentasi.

### Kriteria Keberhasilan
- DAG berhasil berjalan end-to-end secara terjadwal tanpa intervensi manual, menghasilkan prediksi yang tertulis ke PostgreSQL lengkap dengan kolom lineage terisi.
- Simulasi kegagalan di salah satu task (uji coba terkontrol, mis. koneksi database terputus sesaat) menghasilkan retry sesuai konfigurasi, dan jika akhirnya gagal, tidak meninggalkan data di tabel tujuan dalam kondisi tidak konsisten (sebagian tertulis, sebagian tidak).
- Hasil prediksi batch untuk sampel data uji, saat dibandingkan dengan hasil dari inference service package (Orang #1) dipanggil langsung dengan input yang sama, menunjukkan hasil yang identik — verifikasi awal parity sebelum verifikasi otomatis dibangun di Milestone 2.6.
- Untuk sampel baris hasil prediksi, kolom lineage berhasil dipakai untuk menelusuri balik versi model dan snapshot data yang menghasilkannya (uji coba terkontrol: pilih beberapa baris acak, verifikasi penelusurannya benar).

---

## Milestone 2.6 — Isolasi Beban terhadap PostgreSQL

### Lingkup
Menyusun strategi penjadwalan dan/atau optimasi teknis agar beban dari job refresh feature store (Milestone 2.3) dan batch scoring DAG (Milestone 2.5) tidak mendegradasi performa baca real-time API (Orang #3) — berdasarkan baseline nyata dari milestone-milestone sebelumnya (durasi refresh, durasi DAG, ukuran data), bukan asumsi di muka.

### Kenapa Ini Jadi Milestone Terpisah
Dokumen arsitektur (Bagian 6.3) menyatakan risiko ini eksplisit sebagai kesadaran yang harus ada, tapi mekanisme konkretnya sengaja dibiarkan terbuka sampai ada beban nyata untuk dijadikan dasar keputusan. Ini baru bisa dikerjakan dengan baik setelah Milestone 2.3 dan 2.5 berjalan dan menghasilkan data nyata soal karakteristik beban — bukan diputuskan di awal berdasarkan tebakan.

### Output
- Analisis beban nyata: kapan job Milestone 2.3 dan 2.5 memberi tekanan terbesar ke database, dan seberapa besar dampaknya terhadap query baca yang mensimulasikan pola akses real-time API.
- Strategi mitigasi yang dipilih dan diterapkan (mis. penjadwalan di luar jam sibuk, index tambahan, connection pooling, atau read replica bila memang diperlukan pada skala ini) — dipilih berdasarkan hasil analisis, bukan diterapkan seluruhnya secara default.

### Kriteria Keberhasilan
- Simulasi query baca bergaya real-time API yang dijalankan bersamaan dengan job refresh feature store/batch DAG (uji coba terkontrol) menunjukkan latensi yang masih dalam rentang wajar, dibandingkan baseline saat tidak ada job berjalan bersamaan.
- Strategi mitigasi yang diterapkan terdokumentasi beserta alasan pemilihannya, sehingga bisa dievaluasi ulang jika beban bertumbuh di kemudian hari.

---

## Milestone 2.7 — CI/CD dan Verifikasi Parity Otomatis

### Lingkup
Membangun pipeline CI/CD yang menjalankan empat gerbang wajib sesuai Bagian 6.1 dokumen arsitektur: (1) unit test modul transformasi dari Orang #1 dijalankan otomatis setiap ada perubahan kode, (2) gerbang kualitas data (mengintegrasikan pemeriksaan dari Milestone 2.4 ke pipeline CI/CD, bukan hanya berjalan sebagai task DAG terisolasi), (3) verifikasi parity — pengujian otomatis yang membandingkan output batch (lewat pemanggilan DAG atau modul yang sama) dengan output real-time (lewat pemanggilan inference service package langsung, mensimulasikan jalur Orang #3) untuk input yang identik, dan (4) integrasi dengan proses build/deploy service yang dipegang Orang #3 (gerbang test sebelum deployment, dijalankan dari pipeline CI yang sama).

### Kenapa Ini Jadi Milestone Terpisah
Verifikasi parity adalah kontrol yang secara eksplisit dinyatakan di dokumen arsitektur sebagai pembuktian aktif — bukan asumsi — bahwa prinsip satu sumber kebenaran benar-benar terjaga. Ini layak jadi milestone tersendiri (bukan ditempel di akhir Milestone 2.5) karena butuh baik jalur batch maupun cara mensimulasikan jalur real-time sudah tersedia sebagai dasar perbandingan.

### Output
- Pipeline CI/CD yang menjalankan unit test Orang #1 otomatis pada setiap perubahan kode terkait.
- Integrasi gerbang kualitas data (Milestone 2.4) ke pipeline CI/CD sebagai kontrol yang konsisten, bukan hanya logic tertanam di dalam DAG yang sulit diaudit terpisah.
- Test verifikasi parity otomatis: input sampel yang sama dijalankan lewat jalur batch dan jalur real-time (disimulasikan), hasil dibandingkan, perbedaan yang melebihi toleransi wajar menggagalkan pipeline CI.
- Hook/integrasi yang memungkinkan Orang #3 memicu gerbang test miliknya dari pipeline CI yang sama, alih-alih membangun pipeline CI terpisah.

### Kriteria Keberhasilan
- Perubahan kode yang sengaja merusak modul transformasi (uji coba terkontrol) menyebabkan pipeline CI gagal di gerbang unit test, sebelum sempat sampai ke gerbang berikutnya.
- Perubahan yang sengaja membuat jalur batch dan real-time menghasilkan output berbeda untuk input yang sama (uji coba terkontrol, mis. mengubah urutan operasi di satu jalur saja) berhasil terdeteksi oleh test verifikasi parity dan menggagalkan pipeline.
- Orang #3 berhasil mengintegrasikan gerbang deployment miliknya ke pipeline yang sama tanpa perlu membangun infrastruktur CI/CD terpisah.

---

## Milestone 2.8 — Validasi Artifact, Promosi, dan Rollback Versi Model

### Lingkup
Membangun dua gerbang berbeda sesuai Bagian 5.5 dokumen arsitektur: **sanity check artifact** (model dapat dimuat, output berbentuk/bertipe sesuai kontrak, tidak menghasilkan nilai tidak valid untuk input uji) sebagai syarat sebelum artifact layak diregistrasi sebagai kandidat versi baru, dan **verifikasi sebelum promosi** (perbandingan singkat hasil versi kandidat terhadap versi aktif memakai sampel data production terkini) sebelum versi kandidat ditandai aktif. Termasuk mekanisme promosi dan rollback itu sendiri — mengubah penanda versi aktif di MLflow registry (sesuai konvensi Milestone 2.1) dan sebaliknya. Termasuk memastikan kedua jalur (DAG batch di sini, dan real-time API di sisi Orang #3) benar-benar mengambil versi aktif terbaru tanpa langkah manual tambahan di masing-masing sisi setiap kali versi berganti (sesuai prinsip Bagian 5.2 dokumen arsitektur).

### Kenapa Ini Jadi Milestone Terpisah
Ini adalah implementasi konkret dari keputusan arsitektural "rollback = ganti penanda versi, bukan redeploy", sekaligus gerbang kelayakan yang mencegah versi bermasalah sampai jadi versi aktif tanpa verifikasi apa pun selain lolos CI. Layak berdiri sendiri karena kegagalan di sini berarti kegagalan seluruh premis kecepatan-dan-keamanan rollback yang dijanjikan desain ini. Baru relevan dikerjakan setelah registry (Milestone 2.1) dan kedua jalur konsumsi model (DAG di sini, service Orang #3) sudah bisa memuat model berdasarkan versi.

### Output
- Sanity check artifact otomatis, dijalankan sebelum model baru diregistrasi sebagai kandidat versi.
- Mekanisme verifikasi sebelum promosi: perbandingan hasil versi kandidat vs versi aktif terhadap sampel data production, terdokumentasi kriteria kelulusannya.
- Mekanisme/prosedur promosi versi model baru ke status aktif, terdokumentasi (siapa yang berwenang, langkah konkretnya).
- Mekanisme/prosedur rollback ke versi sebelumnya, dengan langkah yang sama sederhananya dengan promosi.
- Verifikasi bahwa DAG batch (Milestone 2.5) secara otomatis memakai versi aktif terbaru pada run berikutnya setelah promosi/rollback, tanpa perlu mengubah kode DAG.

### Kriteria Keberhasilan
- Artifact yang sengaja dirusak (uji coba terkontrol: mis. model yang menghasilkan NaN untuk input valid) berhasil ditolak oleh sanity check, tidak sampai jadi kandidat versi terregistrasi.
- Simulasi promosi versi model baru (uji coba terkontrol) diikuti oleh run DAG berikutnya menghasilkan prediksi dari versi baru tersebut, tanpa intervensi manual di luar langkah promosi itu sendiri.
- Simulasi rollback (uji coba terkontrol, setelah promosi di atas) berhasil mengembalikan DAG ke memakai versi sebelumnya pada run berikutnya, dengan kecepatan yang jauh lebih cepat dibanding hipotesis redeploy penuh.
- Orang #3 mengonfirmasi mekanisme deteksi versi aktif di sisi real-time API bekerja sesuai konvensi yang sama (verifikasi lintas pekerjaan, dijadwalkan bersama Milestone terkait di `mlops-03-deployment-observability.md`).

---

## Catatan Serah Terima ke Pekerjaan Lain

Beberapa hal dari pekerjaan ini menjadi fondasi langsung bagi **Orang #3** (`mlops-03-deployment-observability.md`):

- **Skema feature store** (Milestone 2.2) dan **jaminan keamanan baca saat refresh** (Milestone 2.3) — real-time API akan membaca dari tabel yang sama; perubahan skema di kemudian hari perlu dikomunikasikan sebelum diterapkan, bukan sesudah.
- **Skema tabel hasil prediksi batch, termasuk kolom lineage** (Milestone 2.5) — relevan jika real-time API atau dashboard pihak lain perlu tahu format hasil batch untuk keperluan konsistensi tampilan, dan sebagai acuan kolom lineage yang setara di sisi response real-time API.
- **Konvensi versi aktif MLflow dan mekanisme promosi/rollback** (Milestone 2.1 dan 2.8) — Orang #3 perlu mengikuti konvensi yang sama persis di sisi real-time API, bukan membangun mekanisme deteksi versi terpisah yang berisiko tidak sinkron.
- **Pipeline CI/CD** (Milestone 2.7) — dirancang sebagai infrastruktur bersama yang **diperluas** oleh Orang #3 dengan menambahkan gerbang deployment service miliknya, bukan membangun pipeline CI terpisah, mengikuti prinsip yang sama dengan orchestrator bersama.

Sebaliknya, pekerjaan ini bergantung penuh pada **Orang #1** (`mlops-01-productionization.md`) — khususnya klasifikasi fitur (Milestone 1.1) sebagai dasar desain feature store, dan inference service package (Milestone 1.5) sebagai satu-satunya logika transformasi yang dipanggil di seluruh milestone pekerjaan ini. Jika modul itu berubah (mis. karena retraining menghasilkan versi model dengan fitur baru — lihat Bagian 5.3–5.4 dokumen arsitektur), dampaknya perlu ditelusuri ke Milestone 2.2 (desain feature store) dan Milestone 2.5 (DAG) sebelum versi baru dipromosikan lewat Milestone 2.8.
