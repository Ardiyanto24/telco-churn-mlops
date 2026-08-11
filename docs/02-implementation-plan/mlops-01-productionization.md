# Rancangan Implementasi — Productionization

**MLOps Platform — Telekomunikasi (Churn/Risk Prediction)**

| | |
|---|---|
| **Pemilik pekerjaan** | 1 orang (ML Engineer — Productionization) |
| **Dokumen induk** | `rancangan-arsitektur-mlops-platform.md` (Bagian 2, 3.1, 3.5, 5.4, 6.2) |
| **Cakupan pekerjaan** | Notebook + model artifact (given) → modul transformasi teruji → inference service package siap dipanggil oleh batch pipeline maupun real-time API |
| **Tidak termasuk** | Training dan modeling ulang (sudah selesai — di luar cakupan seluruh sistem); menjalankan pipeline terjadwal (lihat `mlops-02-pipeline-orchestration.md`); deployment ke Kubernetes dan observability (lihat `mlops-03-deployment-observability.md`) |
| **Status dokumen** | Rancangan implementasi kerja — bukan dokumen arsitektur |

---

## Cara Membaca Dokumen Ini

Dokumen ini berisi **milestone**, bukan task list atomic. Setiap milestone:
- Mencakup satu lingkup kerja yang koheren (bukan satu tugas kecil)
- Punya **output** yang jelas dan **kriteria keberhasilan** yang bisa diverifikasi
- **Tidak** menentukan tool atau langkah teknis persis kecuali sudah dinyatakan pasti di dokumen arsitektur induk — sisanya keputusan implementasi di lapangan

Urutan milestone di bawah adalah urutan yang disarankan (mengikuti dependency alami: tidak bisa menulis test sebelum tahu fungsi apa yang mau diuji, tidak bisa membungkus service sebelum modul stabil), bukan urutan kaku. Temuan di satu milestone — misalnya ternyata notebook memakai library dengan versi yang sudah deprecated, atau fitur historis ternyata lebih kompleks dari yang terlihat sekilas — wajar mengubah detail milestone sesudahnya.

Rujukan wajib: `rancangan-arsitektur-mlops-platform.md` Bagian 2 (prinsip mengikat), terutama soal satu sumber kebenaran transformasi, kontrak skema request real-time, dan reproducibility environment — dokumen ini tidak mengutip ulang isinya secara detail, hanya merujuk saat relevan.

---

## Konteks dan Prinsip Kunci yang Perlu Dipegang

Beberapa keputusan dari dokumen arsitektur sudah final dan **membatasi** bagaimana pekerjaan ini dilakukan — bukan pilihan bebas milik pemilik pekerjaan:

- **Satu sumber kebenaran, dipakai dua jalur.** Modul transformasi yang dibangun di sini bukan hanya untuk kebutuhan batch — ia adalah dependency langsung yang dipanggil baik oleh batch scoring DAG (Orang #2) maupun real-time inference API (Orang #3). Modul ini tidak boleh ditulis dengan asumsi "nanti dipanggil dari satu tempat saja"; ia harus pure, tanpa side effect tersembunyi, dan tanpa asumsi implisit soal dari mana datanya dipanggil.
- **Training-serving skew adalah risiko utama yang harus dicegah di titik ini.** Logika preprocessing dan feature engineering yang diekstrak dari notebook harus identik persis dengan yang dipakai saat training — bukan versi "yang mirip" atau "yang disederhanakan untuk production". Kalau ada ambiguitas soal urutan operasi atau parameter di notebook, ini harus dikonfirmasi ke Data Scientist, bukan ditebak.
- **Dua kontrak skema, bukan satu.** Selain skema data mentah di PostgreSQL (untuk jalur batch), ada skema request real-time API yang setara pentingnya (Bagian 3.5 dokumen arsitektur) — field yang dikirim konsumen real-time harus terpetakan eksplisit ke kolom yang sama yang dipakai modul ini. Kedua kontrak ini perlu didefinisikan sadar, bukan salah satu terlewat karena awalnya kelihatan seperti detail API biasa.
- **Reproducibility bukan langkah opsional di akhir.** Versi library yang dipakai untuk membentuk/menyerialisasi model (mis. scikit-learn, xgboost) harus dikunci sejak modularisasi dimulai — bukan ditambal belakangan saat containerization (Orang #3) sudah berjalan dan tiba-tiba model gagal dimuat.
- **Fitur "seketika" vs fitur "historis" perlu dipisah sadar sejak awal.** Sebagian fitur bisa dihitung langsung dari satu baris data (tersedia di request real-time), sebagian butuh agregasi historis (harus lewat feature store, lihat `mlops-02-pipeline-orchestration.md`). Klasifikasi ini adalah keputusan yang lahir dari pekerjaan ini — Orang #2 dan Orang #3 bergantung pada hasilnya untuk merancang feature store dan skema request.

---

## Milestone 1.1 — Audit dan Inventarisasi Notebook

### Lingkup
Membaca dan memahami menyeluruh notebook serta model artifact yang diserahkan — bukan langsung menulis ulang kode. Mencakup: urutan operasi preprocessing yang sebenarnya dipakai (notebook sering dijalankan tidak berurutan, sel dieksekusi ulang, ada kode mati yang tidak lagi relevan), parameter yang di-hardcode, dependency library beserta versinya, dan yang paling penting — daftar lengkap fitur yang dipakai model beserta cara masing-masing dihitung.

Bagian krusial dari milestone ini: mengklasifikasikan setiap fitur menjadi **fitur seketika** (dihitung dari satu baris data yang tersedia langsung) atau **fitur historis/agregat** (butuh melihat rekam jejak lebih dari satu baris/periode). Klasifikasi ini adalah keputusan yang menentukan desain milestone-milestone Orang #2 dan Orang #3 berikutnya (lihat Bagian 2 dokumen arsitektur, prinsip feature store).

### Kenapa Ini Jadi Milestone Terpisah
Membangun modul production tanpa pemahaman menyeluruh atas notebook menghasilkan risiko training-serving skew yang sulit dideteksi belakangan — kesalahan di titik ini tidak langsung terlihat sebagai error, tapi sebagai performa model yang diam-diam lebih buruk di production. Pekerjaan ini murni observasional/analitis, tidak mengubah kode apa pun, sehingga aman dihentikan sewaktu-waktu tanpa risiko ke komponen lain.

### Output
- Dokumentasi urutan operasi preprocessing yang sebenarnya dipakai model (bukan urutan sel di notebook, tapi urutan logis yang benar-benar menghasilkan fitur final).
- Daftar lengkap fitur, diklasifikasikan seketika vs historis/agregat, beserta definisi perhitungan masing-masing.
- Daftar dependency library beserta versi yang dipakai saat training (dari environment asal notebook, bukan asumsi).
- Daftar pertanyaan/ambiguitas yang perlu dikonfirmasi ke Data Scientist, jika ada.

### Kriteria Keberhasilan
- Setiap fitur yang dipakai model punya definisi perhitungan yang eksplisit dan sudah diklasifikasikan seketika/historis.
- Tidak ada langkah preprocessing di notebook yang statusnya masih "tidak yakin apakah ini dipakai atau kode mati" — semua sudah dikonfirmasi.
- Dokumen ini bisa dipakai langsung sebagai acuan Milestone 1.2 tanpa perlu membuka ulang notebook dari nol.

---

## Milestone 1.2 — Modularisasi Preprocessing dan Feature Engineering

### Lingkup
Menerjemahkan logika preprocessing dan feature engineering hasil Milestone 1.1 menjadi fungsi-fungsi modular yang pure — diberi input yang sama, selalu menghasilkan output yang sama, tanpa bergantung pada state tersembunyi atau variabel global. Termasuk mengunci versi dependency library sesuai temuan Milestone 1.1 (lihat prinsip reproducibility di atas).

### Kenapa Ini Jadi Milestone Terpisah
Ini titik paling rawan kesalahan interpretasi sekaligus fondasi seluruh pekerjaan berikutnya — modul yang dihasilkan di sini akan dipanggil dari dua tempat berbeda (batch DAG dan real-time API) yang ditulis oleh dua orang lain. Kesalahan modularisasi di sini menjalar ke keduanya sekaligus, sehingga layak diverifikasi tuntas sebagai unit kerja sendiri sebelum dipakai di titik lain.

### Output
- Fungsi-fungsi modular untuk setiap langkah preprocessing dan feature engineering, terpisah dari fungsi prediksi itu sendiri.
- File dependency yang mengunci versi library sesuai environment training (mis. `requirements.txt`/`pyproject.toml` dengan versi eksplisit, bukan rentang versi longgar).
- Dokumentasi singkat per fungsi: input yang diharapkan, output yang dihasilkan, dan fitur mana (dari daftar Milestone 1.1) yang dihasilkannya.

### Kriteria Keberhasilan
- Setiap fungsi, dipanggil dengan input yang sama berulang kali, menghasilkan output yang identik — tidak ada dependency pada urutan pemanggilan atau state dari pemanggilan sebelumnya.
- Hasil transformasi dari modul ini terhadap sampel data yang sama menghasilkan fitur yang **identik** dengan hasil preprocessing di notebook asli (dibandingkan langsung, bukan diasumsikan cocok).
- Modul dapat diimpor dan dipanggil secara independen tanpa perlu menjalankan notebook maupun bagian lain dari sistem.

---

## Milestone 1.3 — Skema dan Validasi Data Input

### Lingkup
Mendefinisikan skema data input yang valid untuk model ini secara eksplisit — mencakup **dua kontrak terpisah** sesuai prinsip di Bagian 3.5 dokumen arsitektur: skema data mentah dari PostgreSQL (kolom, tipe, nilai yang diperbolehkan) untuk jalur batch, dan skema request untuk jalur real-time API (field, tipe, dan pemetaan eksplisit ke kolom yang sama). Termasuk validasi yang menolak data tidak valid secara eksplisit, bukan meneruskan data salah bentuk ke model secara diam-diam.

### Kenapa Ini Jadi Milestone Terpisah
Dua kontrak skema ini mudah luput karena tidak terlihat sebagai "komponen" yang jelas kepemilikannya — skema PostgreSQL terasa seperti urusan database, skema request terasa seperti urusan API. Memisahkannya sebagai milestone sendiri memastikan keduanya didefinisikan sadar sebagai satu paket yang konsisten, bukan masing-masing didesain terpisah oleh orang berbeda tanpa saling mengacu.

### Output
- Skema/validasi eksplisit untuk data mentah PostgreSQL yang dipakai sebagai input transformasi (nama kolom, tipe, constraint dasar).
- Skema/validasi eksplisit untuk request real-time API, dengan pemetaan field-ke-kolom yang terdokumentasi jelas terhadap skema data mentah.
- Mekanisme penolakan data yang tidak lolos validasi (raise error eksplisit, bukan meneruskan nilai kosong/default secara diam-diam).

### Kriteria Keberhasilan
- Data yang melanggar skema (uji coba terkontrol: kolom hilang, tipe salah, nilai di luar rentang wajar) berhasil ditolak dengan pesan yang jelas menyebutkan bagian mana yang tidak valid.
- Skema request real-time API dan skema data mentah PostgreSQL, saat dibandingkan berdampingan, menunjukkan pemetaan yang konsisten — tidak ada field/kolom yang punya makna sama tapi didefinisikan berbeda.
- Dokumentasi skema ini siap dibagikan ke Orang #2 (untuk kontrak data mentah) dan Orang #3 (untuk kontrak request API).

---

## Milestone 1.4 — Unit Test untuk Modul Transformasi

### Lingkup
Menulis pengujian otomatis untuk setiap fungsi modular hasil Milestone 1.2 — memverifikasi setiap fungsi bekerja sesuai ekspektasi pada kasus normal, kasus tepi (nilai kosong yang bermakna, nilai ekstrem), dan kasus yang seharusnya ditolak oleh validasi skema (Milestone 1.3).

### Kenapa Ini Jadi Milestone Terpisah
Modul ini akan dipanggil oleh kode yang ditulis dua orang lain yang tidak selalu paham detail internal transformasi — unit test di sini menjadi jaring pengaman utama yang mendeteksi regresi lebih awal, sebelum kesalahan sampai ke batch pipeline atau real-time API dan terlihat sebagai bug yang membingungkan di titik yang jauh dari akar masalahnya.

### Output
- Rangkaian unit test untuk seluruh fungsi modular, mencakup kasus normal, tepi, dan kasus yang harus ditolak validasi.
- Test khusus yang membandingkan output modul terhadap sampel data dan hasil yang sudah diverifikasi cocok dengan notebook asli (regresi terhadap Milestone 1.2).
- Konfigurasi agar test ini bisa dijalankan otomatis sebagai bagian CI/CD (lihat Bagian 6.1 dokumen arsitektur — gerbang kode transformasi menjadi tanggung jawab Orang #2 untuk diintegrasikan, tapi test itu sendiri ditulis di sini).

### Kriteria Keberhasilan
- Seluruh fungsi modular punya cakupan test yang mencakup setidaknya satu kasus normal dan satu kasus tepi per fungsi.
- Test berjalan hijau (lolos) secara konsisten dan dapat dijalankan tanpa dependency eksternal (mis. tanpa perlu koneksi database sungguhan untuk unit test murni).
- Percobaan sengaja merusak salah satu fungsi (uji coba terkontrol) menyebabkan test yang relevan gagal — membuktikan test benar-benar mendeteksi regresi, bukan sekadar ada tapi tidak efektif.

---

## Milestone 1.5 — Inference Service Package

### Lingkup
Membungkus modul transformasi dan model menjadi satu paket yang bisa dipanggil pihak lain secara konsisten — antarmuka pemanggilan yang jelas (fungsi/kelas dengan kontrak input-output yang terdokumentasi), tanpa mengasumsikan bagaimana pemanggil akan menjalankannya (apakah dari dalam DAG batch atau dari dalam service real-time API adalah keputusan Orang #2/#3, bukan diasumsikan di sini). Termasuk memastikan paket ini bisa memuat model dari MLflow registry sesuai versi yang diminta, bukan mengasumsikan hanya ada satu model statis.

### Kenapa Ini Jadi Milestone Terpisah
Ini titik penyelesaian pekerjaan Orang #1 sebagai aset yang dikonsumsi dua pekerjaan lain sekaligus — perlu berdiri sebagai unit kerja sendiri yang stabil dan terverifikasi sebelum Orang #2 dan Orang #3 mulai membangun bagian yang bergantung padanya (lihat dependency keras di Bagian 4 dokumen arsitektur).

### Output
- Package/library terinstal yang membungkus modul transformasi + pemanggilan model, dengan API pemanggilan yang terdokumentasi (fungsi `predict(input) -> output` atau setara).
- Mekanisme pemuatan model dari MLflow registry berdasarkan versi (bukan path file statis yang di-hardcode).
- Dokumentasi cara pakai untuk Orang #2 dan Orang #3: cara instalasi/impor, kontrak input-output, dan contoh pemanggilan.

### Kriteria Keberhasilan
- Package dapat diinstal dan dipanggil dari luar konteks pengembangan Orang #1 (mis. dari environment/proyek terpisah) tanpa perlu mengubah kode internalnya.
- Pemanggilan dengan data uji yang identik menghasilkan output yang identik dengan hasil notebook asli (verifikasi akhir end-to-end, bukan hanya per-fungsi seperti di Milestone 1.4).
- Mekanisme pemuatan model berdasarkan versi berhasil diuji dengan memuat lebih dari satu versi model (uji coba terkontrol) dan menghasilkan hasil yang sesuai versi yang diminta.

---

## Milestone 1.6 — Kontrak Skema dengan Sumber Data

### Lingkup
Menetapkan kesepakatan eksplisit dengan pemilik/sumber data PostgreSQL soal struktur tabel yang jadi input model — kolom apa saja yang tersedia, tipe data, semantik kolom yang berpotensi ambigu (mis. bagaimana nilai kosong diperlakukan, satuan angka, zona waktu timestamp). Termasuk menyepakati bagaimana perubahan skema di sumber data akan dikomunikasikan ke depan, supaya tidak jadi kejutan yang baru ketahuan saat pipeline sudah berjalan.

### Kenapa Ini Jadi Milestone Terpisah
Berbeda sifat dari milestone lain — ini bukan pekerjaan internal yang bisa diselesaikan sendiri, melainkan kesepakatan dengan pihak/sistem eksternal (sumber data). Perlu berdiri sebagai unit kerja eksplisit karena tanpa kontrak yang jelas, Orang #1 (dan pekerjaan hilir lainnya) akan terus menebak-nebak setiap kali skema production berubah.

### Output
- Dokumentasi skema tabel sumber yang disepakati (kolom, tipe, semantik), menjadi rujukan bersama Milestone 1.1–1.3.
- Kesepakatan jalur komunikasi untuk perubahan skema di kemudian hari (siapa yang perlu diberi tahu, lewat kanal apa).

### Kriteria Keberhasilan
- Skema yang didokumentasikan sudah diverifikasi cocok dengan struktur tabel sungguhan di PostgreSQL (bukan asumsi dari dokumentasi lama yang mungkin sudah usang).
- Ada kesepakatan tertulis (meski sederhana) soal jalur komunikasi perubahan skema — bukan diasumsikan "akan tahu sendiri kalau berubah".

---

## Catatan Serah Terima ke Pekerjaan Lain

Package hasil Milestone 1.5, beserta skema/kontrak dari Milestone 1.3 dan 1.6, menjadi **fondasi langsung** bagi kedua pekerjaan lain:

- **Orang #2** (`mlops-02-pipeline-orchestration.md`) memanggil modul transformasi dan inference service ini di dalam batch scoring DAG, dan bergantung pada klasifikasi fitur seketika/historis dari Milestone 1.1 untuk merancang feature store.
- **Orang #3** (`mlops-03-deployment-observability.md`) memanggil package yang sama di dalam real-time inference service, dan bergantung pada skema request API dari Milestone 1.3 untuk mendesain kontrak endpoint-nya.

Perubahan pada modul transformasi atau skema di kemudian hari — misalnya karena model diretrain dengan fitur baru (lihat Bagian 5.3–5.4 dokumen arsitektur soal kontrak retraining) — perlu dikomunikasikan ke keduanya karena berdampak langsung pada kode yang mereka bangun di atasnya. Sebaliknya, jika Orang #2 atau Orang #3 menemukan bahwa hasil batch dan real-time tidak konsisten untuk input yang sama (pelanggaran prinsip verifikasi parity di Bagian 3.5 dokumen arsitektur), titik pertama yang perlu diperiksa adalah apakah keduanya benar-benar memanggil modul yang sama dari pekerjaan ini — bukan diam-diam membangun logika transformasi terpisah di masing-masing sisi.
