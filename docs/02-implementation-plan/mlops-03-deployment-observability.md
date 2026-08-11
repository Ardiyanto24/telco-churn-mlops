# Rancangan Implementasi — Deployment & Observability

**MLOps Platform — Telekomunikasi (Churn/Risk Prediction)**

| | |
|---|---|
| **Pemilik pekerjaan** | 1 orang (MLOps/Infra Engineer — Deployment & Observability) |
| **Dokumen induk** | `rancangan-arsitektur-mlops-platform.md` (Bagian 2, 3.3, 3.5, 5.2–5.4, 6.1, 8) |
| **Cakupan pekerjaan** | Inference service package (dari `mlops-01-productionization.md`) → containerization → real-time inference API di Kubernetes → observability menyeluruh (infra, drift, pipeline health) → dashboard internal (Grafana) dan dashboard publik (web + API), alerting, dan rollback |
| **Tidak termasuk** | Membangun modul transformasi/inference service package itu sendiri (lihat `mlops-01-productionization.md`); batch scoring DAG, feature store, CI/CD inti, dan model registry (lihat `mlops-02-pipeline-orchestration.md`) — pekerjaan ini mengonsumsi dan memperluas keduanya, bukan membangun ulang |
| **Status dokumen** | Rancangan implementasi kerja — bukan dokumen arsitektur |

---

## Cara Membaca Dokumen Ini

Sama seperti dua dokumen lain di proyek ini: berisi **milestone**, bukan task list atomic. Tiap milestone punya lingkup, alasan kenapa dipisah, output, dan kriteria keberhasilan yang bisa diverifikasi. Urutan di bawah adalah urutan yang disarankan, bukan urutan kaku — temuan di satu milestone (mis. pola trafik real-time yang ternyata berbeda dari perkiraan) wajar mengubah detail milestone sesudahnya, khususnya untuk connection pooling dan resource sizing yang memang sengaja belum ditentukan di dokumen arsitektur.

Rujukan wajib: `rancangan-arsitektur-mlops-platform.md` Bagian 2 (prinsip mengikat, terutama kontrak skema request, rollback via registry, dan kontrak kegagalan API), Bagian 5.2–5.4 (siklus hidup model), dan Bagian 8 (observability) — dokumen ini tidak mengutip ulang isinya secara detail, hanya merujuk saat relevan.

---

## Konteks dan Prinsip Kunci yang Perlu Dipegang

Beberapa keputusan dari dokumen arsitektur sudah final dan **membatasi** bagaimana pekerjaan ini dilakukan:

- **Pekerjaan ini memakai, bukan membangun ulang, logika transformasi.** Real-time API di sini memanggil inference service package dari Orang #1 (Milestone 1.5) — bukan reimplementasi logika preprocessing demi kecepatan atau kemudahan integrasi. Sekecil apa pun godaan untuk "menyederhanakan" transformasi di titik ini, itu adalah pelanggaran terhadap prinsip satu sumber kebenaran yang mengikat seluruh sistem.
- **Skema request API bukan keputusan bebas — ini kontrak yang sudah dipetakan.** Milestone 1.3 di `mlops-01-productionization.md` sudah mendefinisikan pemetaan field request ke kolom data mentah. Pekerjaan ini mengimplementasikan kontrak itu, bukan mendesain skema request dari nol berdasarkan selera desain API semata.
- **Rollback model berarti mengubah penanda versi aktif di MLflow, bukan redeploy container.** Service di sini harus dirancang untuk mendeteksi/mengambil model versi aktif tanpa restart penuh setiap kali versi berganti — mengikuti konvensi yang sudah disepakati di Milestone 2.1 dan diimplementasikan di Milestone 2.8 (`mlops-02-pipeline-orchestration.md`). Rollback *deployment* (container/image) adalah mekanisme terpisah untuk kasus berbeda (deployment baru gagal health check), bukan pengganti rollback model.
- **Kontrak kegagalan API adalah keputusan desain, bukan detail teknis belakangan.** Ketika model gagal dimuat atau feature store tidak terjangkau, API wajib mengembalikan error yang terstruktur dan jelas — bukan diam-diam mengembalikan nilai yang terlihat seperti prediksi valid. Konsumen real-time perlu bisa membedakan "risiko rendah" dari "sistem sedang gagal menjawab".
- **Observability bukan pekerjaan yang berdiri sendiri secara konten** — meski kepemilikan teknis dashboard dan alerting ada di sini, isinya kolaboratif: metrik model/drift dari Orang #1, metrik orchestration dari Orang #2. Pekerjaan ini merangkai, bukan menentukan sendiri apa yang relevan dipantau dari sisi model dan pipeline.
- **Dua dashboard, satu sumber data monitoring.** Dashboard internal (Grafana) dan dashboard publik (web custom, untuk kebutuhan portofolio karena tier gratis Grafana tidak mendukung publicly shared dashboard) sengaja dibuat menampilkan cakupan yang sama. PostgreSQL adalah sumber utama data monitoring bagi keduanya (Bagian 8.3 dokumen arsitektur) — bukan Prometheus di-query langsung oleh salah satu dashboard sementara yang lain dari PostgreSQL. Dashboard publik tidak pernah mengakses Grafana atau kredensial internal secara langsung; ia dilayani lewat API publik read-only yang membaca dari PostgreSQL.

---

## Milestone 3.1 — Containerization dan Environment Konsisten

### Lingkup
Membungkus inference service package dari Orang #1 ke dalam container (Docker), memastikan environment production (versi Python, versi library, terutama library ML yang dipakai model) konsisten persis dengan yang dikunci di Milestone 1.2 (`mlops-01-productionization.md`) — bukan environment yang "kelihatannya sama" tapi sebenarnya berbeda versi minor yang bisa menyebabkan model gagal dimuat atau berperilaku berbeda.

### Kenapa Ini Jadi Milestone Terpisah
Ini prasyarat murni infrastruktur sebelum service apa pun bisa dijalankan di Kubernetes — dipisah dari milestone desain API (berikutnya) agar masalah environment/dependency tidak tercampur dengan masalah desain kontrak endpoint. Konsisten dengan prinsip reproducibility yang sudah dikunci sejak Milestone 1.2 di dokumen Orang #1 — pekerjaan ini menjaga, bukan membangun ulang, kedisiplinan itu.

### Output
- Container image yang membungkus inference service package, dengan dependency terkunci sesuai Milestone 1.2 Orang #1.
- Verifikasi bahwa model dapat dimuat dan menghasilkan output yang identik di dalam container dibanding saat dijalankan langsung di environment pengembangan.

### Kriteria Keberhasilan
- Container berhasil di-build dan dijalankan, memuat model dari MLflow registry tanpa error versi/dependency.
- Prediksi terhadap sampel data uji yang sama, dijalankan di dalam container, menghasilkan output identik dengan hasil dari inference service package yang dijalankan langsung oleh Orang #1 (verifikasi ulang parity di titik containerization, bukan diasumsikan otomatis sama).

---

## Milestone 3.2 — Real-Time Inference API

### Lingkup
Membangun service API yang menerima request sesuai skema Milestone 1.3 (`mlops-01-productionization.md`), mengambil fitur seketika dari payload request, mengambil fitur historis dari feature store (skema dari Milestone 2.2, `mlops-02-pipeline-orchestration.md`), menjalankan transformasi lewat inference service package, dan mengembalikan prediksi dari model versi aktif — termasuk kolom lineage (versi model dan waktu prediksi dibuat) di setiap response, setara dengan kolom lineage di tabel hasil batch (Bagian 5.6 dokumen arsitektur). Termasuk implementasi kontrak kegagalan (error terstruktur saat model/feature store tidak terjangkau atau request tidak valid) sesuai prinsip di atas.

### Kenapa Ini Jadi Milestone Terpisah
Ini titik integrasi inti dari seluruh jalur real-time — baru bisa dibangun dengan baik setelah container dasar (Milestone 3.1) stabil dan kedua kontrak (skema request dari Orang #1, skema feature store dari Orang #2) sudah tersedia sebagai acuan pasti, bukan ditebak.

### Output
- Endpoint API yang menerima request, memvalidasi sesuai skema, mengambil fitur dari kedua sumber (payload + feature store), dan mengembalikan prediksi lengkap dengan versi model dan waktu prediksi di response.
- Mekanisme error terstruktur untuk skenario kegagalan: request tidak valid, feature store tidak terjangkau, model gagal dimuat.
- Dokumentasi API (skema request/response, kode error, contoh pemanggilan).

### Kriteria Keberhasilan
- Request valid dengan data uji menghasilkan prediksi yang **identik** dengan hasil batch (Milestone 2.5, `mlops-02-pipeline-orchestration.md`) untuk entity dan periode data yang sama — verifikasi parity end-to-end pada jalur nyata, bukan simulasi.
- Request tidak valid (uji coba terkontrol: field hilang, tipe salah) ditolak dengan error terstruktur yang jelas, bukan diteruskan ke model atau menghasilkan error tak terduga.
- Simulasi feature store tidak terjangkau atau model gagal dimuat (uji coba terkontrol) menghasilkan error yang bisa dibedakan jelas dari prediksi valid oleh pemanggil.
- Response API untuk sampel request uji menyertakan versi model dan waktu prediksi yang benar dan konsisten dengan versi aktif saat itu di registry.

---

## Milestone 3.3 — Deployment ke Kubernetes

### Lingkup
Men-deploy container dari Milestone 3.1–3.2 ke Kubernetes — konfigurasi deployment, service, resource request/limit awal (CPU/memori), dan health check yang mencerminkan kesiapan service sesungguhnya (bukan sekadar proses hidup, tapi model sudah termuat dan siap melayani request).

### Kenapa Ini Jadi Milestone Terpisah
Ini pekerjaan operasional yang berbeda sifat dari membangun logic API itu sendiri (Milestone 3.2) — layak dipisah agar konfigurasi deployment bisa diiterasi (resource sizing, health check) tanpa harus menyentuh kode aplikasi setiap kali.

### Output
- Manifest/konfigurasi deployment Kubernetes untuk real-time API, dengan resource request/limit awal.
- Health check (readiness dan liveness) yang mencerminkan kesiapan model, bukan hanya proses berjalan.
- Service dapat diakses dan diuji dari luar cluster (atau dari lingkungan uji yang merepresentasikan konsumen real-time).

### Kriteria Keberhasilan
- Service berhasil berjalan di Kubernetes dan merespons request dengan hasil yang konsisten dengan Milestone 3.2.
- Simulasi model belum termuat (mis. saat container baru start) menyebabkan readiness check gagal — service tidak menerima trafik sebelum benar-benar siap, bukan menerima request dan gagal di tengah jalan.
- Resource request/limit awal terdokumentasi beserta dasar penentuannya (meski masih berupa estimasi awal — lihat Milestone 3.7 untuk penyesuaian berdasar beban nyata).

---

## Milestone 3.4 — Deteksi Versi Model Aktif Tanpa Restart Penuh

### Lingkup
Mengimplementasikan mekanisme di sisi service yang memungkinkan real-time API mendeteksi dan mengambil model versi aktif terbaru dari MLflow registry — mengikuti konvensi yang sama persis dengan Milestone 2.1 dan 2.8 (`mlops-02-pipeline-orchestration.md`) — tanpa memerlukan restart/redeploy penuh setiap kali promosi atau rollback versi terjadi di sisi Orang #2.

### Kenapa Ini Jadi Milestone Terpisah
Ini implementasi konkret dari janji arsitektural "rollback cepat" (Bagian 5.2 dokumen arsitektur) di sisi jalur real-time — kegagalan di sini berarti rollback yang seharusnya cepat (cukup ganti penanda versi di registry) tetap lambat karena service real-time tidak ikut ter-update tanpa campur tangan manual. Baru relevan dikerjakan setelah API dasar (Milestone 3.2–3.3) stabil dan mekanisme promosi/rollback di sisi Orang #2 (Milestone 2.8) sudah berjalan sebagai acuan verifikasi bersama.

### Output
- Mekanisme deteksi versi aktif (polling berkala, webhook, atau setara) terpasang di service.
- Verifikasi bersama Orang #2: simulasi promosi/rollback versi menghasilkan service ini benar-benar berpindah ke versi yang sesuai tanpa restart manual.

### Kriteria Keberhasilan
- Simulasi promosi versi baru di registry (dikoordinasikan dengan Milestone 2.8 Orang #2) diikuti oleh service ini mulai menghasilkan prediksi dari versi baru dalam rentang waktu yang wajar, tanpa restart/redeploy manual.
- Simulasi rollback (uji coba terkontrol, sama seperti di atas) menghasilkan service kembali memakai versi sebelumnya dengan kecepatan yang sesuai ekspektasi "rollback cepat" yang dijanjikan desain.

---

## Milestone 3.5 — Monitoring Infra dan Pipeline Health

### Lingkup
Membangun pemantauan metrik infrastruktur untuk real-time API (latency, throughput, error rate) dan mengonsolidasikan sinyal kesehatan pipeline batch dari Orang #2 (status DAG, status refresh feature store, status tulis-balik ke PostgreSQL) ke satu tempat yang bisa dipantau tim — bukan membangun ulang mekanisme pencatatan status itu sendiri (itu sudah ada sebagai bagian kerja Orang #2), tapi mengumpulkan dan menyajikannya.

### Kenapa Ini Jadi Milestone Terpisah
Ini kapabilitas paling dasar dari tiga jenis sinyal observability yang disebut di dokumen arsitektur (Bagian 8) — sebelum bicara soal drift, tim harus lebih dulu punya visibilitas dasar atas apakah service dan pipeline berjalan sehat. Independen dari milestone drift (berikutnya), bisa dikerjakan lebih dulu atau paralel.

### Output
- Metrik infra real-time API: latency (p50/p95/p99), throughput, error rate — dipantau dan tersimpan sebagai riwayat, bukan hanya snapshot sesaat.
- Konsolidasi status pipeline batch (dari Orang #2) ke tempat yang sama, tanpa perlu tim membuka sistem orchestrator secara terpisah untuk tahu statusnya.

### Kriteria Keberhasilan
- Untuk real-time API, tim bisa menjawab "berapa latency p95 hari ini" dan "berapa persen request gagal" tanpa query manual ke log mentah.
- Untuk pipeline batch, status run terakhir (berhasil/gagal, durasi) terlihat di tempat yang sama tanpa membuka orchestrator Orang #2 secara langsung.

---

## Milestone 3.6 — Monitoring Drift dan Kualitas Model

### Lingkup
Membangun pemantauan distribusi fitur input dan distribusi output prediksi dari waktu ke waktu, dibandingkan terhadap baseline data training — bekerja sama dengan Orang #1 untuk menentukan fitur mana yang paling relevan dipantau dan ambang batas yang dianggap signifikan (sesuai catatan ketergantungan di Bagian 10 dokumen arsitektur: threshold ini digali bersama, bukan diputuskan sepihak di sini).

### Kenapa Ini Jadi Milestone Terpisah
Berbeda sifat dari Milestone 3.5 — ini bicara soal **kebenaran dan kewajaran** prediksi model dari waktu ke waktu, bukan sekadar status hidup/mati service. Baru bisa dikerjakan dengan baik setelah service berjalan cukup lama untuk punya data produksi sungguhan sebagai pembanding, dan setelah berdiskusi dengan Orang #1 soal fitur dan ambang batas yang relevan secara model.

### Output
- Pemantauan distribusi fitur input (dari kedua jalur — batch dan real-time) dibanding baseline data training.
- Pemantauan distribusi output prediksi dari waktu ke waktu.
- Ambang batas drift yang disepakati bersama Orang #1, dengan mekanisme alert saat terlampaui.

### Kriteria Keberhasilan
- Pergeseran distribusi fitur buatan (uji coba terkontrol, mis. menyuntik data uji dengan pola berbeda dari baseline) berhasil terdeteksi dan memicu sinyal yang terlihat di dashboard.
- Ambang batas yang dipakai terdokumentasi beserta alasan pemilihannya bersama Orang #1 — bukan angka default yang tidak dipahami asal-usulnya.

---

## Milestone 3.7 — Jalur Notifikasi Retraining ke Data Scientist

### Lingkup
Mengimplementasikan kontrak retraining dari Bagian 5.3 dokumen arsitektur secara konkret: menyepakati dan membangun jalur notifikasi ke tim Data Scientist eksternal ketika drift (Milestone 3.6) melewati ambang batas — mencakup kanal komunikasi yang dipakai, informasi apa yang disertakan dalam notifikasi (metrik apa yang melewati ambang, sejak kapan, data pembanding apa), dan kejelasan bahwa retraining sendiri tetap dilakukan pihak eksternal, bukan dipicu otomatis oleh sistem ini kecuali disepakati lain.

### Kenapa Ini Jadi Milestone Terpisah
Dokumen arsitektur eksplisit menyatakan ini sebagai kontrak yang harus ada, bukan dibiarkan implisit — monitoring drift tanpa jalur tindak lanjut hanya menghasilkan dashboard yang dilihat tapi tidak memicu aksi. Baru relevan dikerjakan setelah mekanisme deteksi drift (Milestone 3.6) sudah berjalan dan bisa dijadikan pemicu nyata.

### Output
- Kesepakatan tertulis dengan tim Data Scientist: kanal notifikasi, informasi yang disertakan, dan ekspektasi tindak lanjut.
- Mekanisme teknis yang mengirim notifikasi tersebut secara otomatis saat ambang batas Milestone 3.6 terlampaui.

### Kriteria Keberhasilan
- Simulasi drift melewati ambang batas (uji coba terkontrol) berhasil memicu notifikasi ke kanal yang disepakati, dengan informasi yang cukup bagi tim Data Scientist untuk memahami apa yang terjadi tanpa perlu bertanya balik detail dasar.
- Tim Data Scientist mengonfirmasi jalur dan format notifikasi ini dapat mereka pakai sebagai dasar keputusan retraining.

---

## Milestone 3.8 — Dashboard dan Alerting Terpadu

### Lingkup
Menyatukan hasil Milestone 3.5 (infra & pipeline health) dan 3.6 (drift & kualitas model) ke dalam satu dashboard yang mencerminkan kesehatan sistem secara keseluruhan, beserta jalur alerting yang jelas (siapa menerima alert apa, lewat kanal apa) — termasuk memastikan isi dashboard ini benar-benar kolaboratif: metrik yang relevan secara model diverifikasi bersama Orang #1, metrik orchestration diverifikasi bersama Orang #2.

### Kenapa Ini Jadi Milestone Terpisah
Ini murni pekerjaan konsolidasi dan presentasi — sengaja diletakkan setelah komponen individualnya (3.5, 3.6, 3.7) menghasilkan data yang bisa ditampilkan, bukan dibangun kosong di awal lalu diisi belakangan.

### Output
- Dashboard tunggal yang mencerminkan kesehatan real-time API, pipeline batch, dan drift model.
- Konfigurasi alerting dengan tujuan/kanal yang jelas per jenis kejadian.

### Kriteria Keberhasilan
- Dashboard dapat diakses tim dan mencerminkan kondisi terkini (bukan data basi).
- Orang #1 dan Orang #2 mengonfirmasi metrik yang relevan dari sisi mereka masing-masing sudah terwakili dengan benar di dashboard ini.
- Simulasi kegagalan di satu titik (uji coba terkontrol, mis. DAG batch gagal) menghasilkan alert yang jelas menunjukkan titik akar tersebut ke kanal yang tepat.

---

## Milestone 3.9 — Penyimpanan Data Monitoring di PostgreSQL

### Lingkup
Merancang dan membangun skema tabel di PostgreSQL sebagai sumber utama data monitoring — menyimpan hasil agregasi periodik dari ketiga pilar observability (infra/operational, drift, pipeline health) yang sudah dikumpulkan di Milestone 3.5–3.6, bukan metrik mentah resolusi tinggi. Termasuk job/mekanisme yang menulis agregasi ini secara berkala dari sumber metrik asal (mis. Prometheus untuk metrik infra) ke tabel PostgreSQL tersebut.

### Kenapa Ini Jadi Milestone Terpisah
Ini fondasi yang mewujudkan prinsip "PostgreSQL sebagai satu sumber data monitoring" (Bagian 8.3 dokumen arsitektur) secara konkret — harus ada dan stabil sebelum Grafana dan dashboard publik (Milestone 3.10) sama-sama bisa membaca dari tempat yang sama. Dipisah dari Milestone 3.8 karena sifatnya berbeda: 3.8 merangkai tampilan dari sumber yang sudah ada, sementara ini membangun sumber data barunya.

### Output
- Skema tabel monitoring di PostgreSQL (metrik apa, granularitas waktu, dari pilar mana).
- Mekanisme agregasi periodik dari sumber metrik asal (mis. Prometheus) ke tabel ini, dengan frekuensi yang dipilih sadar (mis. per menit), bukan real-time mentah.
- Konfigurasi Grafana diarahkan membaca dari tabel PostgreSQL ini untuk metrik yang relevan, bukan langsung ke Prometheus untuk metrik yang sama.

### Kriteria Keberhasilan
- Nilai agregasi di tabel PostgreSQL, saat dibandingkan dengan nilai mentah di Prometheus untuk periode yang sama, menunjukkan hasil agregasi yang benar (bukan sekadar tersalin, tapi teragregasi sesuai definisi yang dipilih).
- Dashboard Grafana yang sudah dikonfigurasi membaca dari PostgreSQL (bukan Prometheus langsung) menampilkan data yang sama benarnya dengan sebelum perpindahan sumber.
- Job agregasi berjalan terjadwal dan konsisten, tanpa celah waktu yang membuat data di PostgreSQL basi dibanding kondisi nyata.

---

## Milestone 3.10 — API Publik dan Dashboard Monitoring Publik

### Lingkup
Membangun API read-only yang membaca data monitoring dari PostgreSQL (Milestone 3.9) dengan scope akses yang dibatasi ketat (hanya tabel monitoring yang dimaksudkan publik, tidak ada jalur ke kredensial atau tabel produksi lain), dan dashboard web custom yang mengonsumsi API ini — ditujukan untuk kebutuhan portofolio, dapat diakses publik tanpa login, sengaja dibuat menampilkan cakupan yang sama dengan dashboard internal (Milestone 3.8). Cakupan konten yang benar-benar dipublikasikan (apakah identik penuh dengan dashboard internal atau ada yang dikecualikan) didiskusikan dan diputuskan di titik ini, bukan diasumsikan dari awal.

### Kenapa Ini Jadi Milestone Terpisah
API dan dashboard publik adalah concern yang berbeda dari dashboard internal (Milestone 3.8) — keduanya perlu dibangun dengan kesadaran keamanan yang lebih ketat karena dapat diakses siapa pun tanpa autentikasi, sehingga layak diverifikasi terpisah sebagai unit kerja sendiri. Baru bisa dikerjakan dengan baik setelah data monitoring tersedia terstruktur di PostgreSQL (Milestone 3.9) sebagai sumber yang pasti, bukan ditebak.

### Output
- Service API publik (read-only, tanpa autentikasi, dengan rate limiting) yang menampilkan data monitoring dari PostgreSQL.
- Role/kredensial PostgreSQL khusus untuk API ini, dibatasi ketat ke tabel monitoring yang memang dimaksudkan publik — bukan memakai kredensial yang sama dengan mekanisme internal (Milestone 3.9) atau jalur data produksi lain.
- Dashboard web publik yang mengonsumsi API ini, di-deploy dapat diakses publik.
- Keputusan terdokumentasi soal cakupan konten yang dipublikasikan, beserta alasannya.

### Kriteria Keberhasilan
- Endpoint API dapat diakses publik (tanpa login) dan mengembalikan data yang konsisten dengan tabel monitoring di PostgreSQL.
- Kredensial API publik terbukti **tidak bisa** mengakses tabel di luar whitelist monitoring saat diuji coba (mis. tidak bisa mengakses tabel hasil prediksi, feature store, atau kredensial lain).
- Dashboard publik dan dashboard internal (Grafana), saat dibandingkan berdampingan untuk periode yang sama, menunjukkan data yang konsisten sesuai cakupan yang sudah diputuskan — tidak ada perbedaan nilai yang tidak dijelaskan.
- Rate limiting per IP pada API publik terbukti aktif saat diuji coba terkontrol.

---

## Milestone 3.11 — Rollback Deployment dan Resource Sizing

### Lingkup
Membangun kemampuan rollback deployment di level Kubernetes (terpisah dari rollback versi model di Milestone 3.4/2.8) — untuk skenario deployment kode/container baru yang gagal health check atau menunjukkan perilaku tidak sehat, bukan skenario model bermasalah. Termasuk meninjau ulang resource request/limit awal (Milestone 3.3) berdasarkan beban nyata yang sudah teramati lewat monitoring (Milestone 3.5), dan menyiapkan konfigurasi dasar autoscaling jika pola trafik menunjukkan kebutuhan itu.

### Kenapa Ini Jadi Milestone Terpisah
Rollback deployment dan rollback model adalah dua mekanisme berbeda yang menangani dua jenis kegagalan berbeda (Bagian 6.1 dokumen arsitektur membedakan keduanya eksplisit) — layak dipisah agar tidak tercampur secara konsep maupun implementasi. Resource sizing sengaja ditunda ke titik ini karena butuh data beban nyata dari Milestone 3.5, bukan diputuskan sebagai tebakan di Milestone 3.3.

### Output
- Mekanisme rollback deployment di Kubernetes (mis. memakai kemampuan native seperti rollout undo, atau setara) terverifikasi bekerja.
- Resource request/limit yang sudah disesuaikan berdasarkan data beban nyata, beserta konfigurasi autoscaling dasar jika relevan.

### Kriteria Keberhasilan
- Simulasi deployment baru yang gagal health check (uji coba terkontrol) berhasil di-rollback ke versi deployment sebelumnya, dengan downtime yang minimal.
- Resource request/limit yang disesuaikan terbukti tidak menyebabkan service throttled/OOM pada beban puncak yang teramati, sekaligus tidak boros dibanding kebutuhan nyata.

---

## Milestone 3.12 — Runbook Operasional

### Lingkup
Menyusun satu dokumen operasional ringkas yang merangkum skenario kegagalan umum di seluruh sistem dan langkah responsnya — drift terdeteksi (rujuk Milestone 3.6–3.7), DAG batch gagal (rujuk mekanisme di `mlops-02-pipeline-orchestration.md`), real-time API down atau merespons lambat (rujuk Milestone 3.5), dashboard/API publik bermasalah (rujuk Milestone 3.9–3.10), kebutuhan rollback mendesak baik versi model (rujuk Milestone 3.4) maupun deployment (rujuk Milestone 3.11). Bukan dokumen arsitektur baru — murni ringkasan praktis "kalau terjadi X, langkah apa yang diambil, siapa yang perlu tahu" yang merujuk balik ke milestone/dokumen yang relevan untuk detail lengkapnya.

### Kenapa Ini Jadi Milestone Terpisah
Pengetahuan penanganan insiden saat ini tersebar di berbagai bagian "Kenapa Ini Jadi Milestone Terpisah" di tiga dokumen — berguna untuk memahami desain, tapi tidak praktis dipakai saat insiden nyata sedang berlangsung dan waktu terbatas. Sengaja diletakkan di akhir karena baru bisa disusun dengan baik setelah seluruh mekanisme yang dirujuknya (observability, rollback) benar-benar berjalan, bukan berupa prosedur hipotetis yang belum pernah diuji.

### Output
- Dokumen runbook yang mencakup skenario kegagalan utama, dengan langkah respons singkat dan rujukan ke milestone/dokumen terkait untuk detail.
- Runbook diuji terhadap setidaknya satu skenario simulasi untuk memastikan langkahnya benar-benar bisa diikuti, bukan hanya benar secara teori.

### Kriteria Keberhasilan
- Untuk setiap skenario kegagalan utama yang sudah diuji coba terkontrol di milestone-milestone sebelumnya (drift, DAG gagal, API down, rollback), ada entri runbook yang jelas dan bisa diikuti tanpa perlu membuka ulang seluruh dokumen rancangan.
- Simulasi insiden baru (uji coba terkontrol, salah satu skenario di atas) berhasil ditangani mengikuti langkah di runbook, tanpa perlu improvisasi besar di luar apa yang tertulis.

---

## Catatan Serah Terima

Pekerjaan ini adalah titik akhir dari seluruh rangkaian — tidak ada pekerjaan lain yang bergantung pada hasil di sini sebagai fondasi lebih lanjut, kecuali konsumen akhir sistem (dashboard/laporan yang membaca hasil batch, dan sistem lain yang memanggil real-time API).

Pekerjaan ini bergantung penuh pada dua pekerjaan lain: **Orang #1** (`mlops-01-productionization.md`) untuk inference service package, skema request, dan definisi fitur/threshold drift; **Orang #2** (`mlops-02-pipeline-orchestration.md`) untuk skema feature store, konvensi versi model, mekanisme promosi/rollback di registry, dan pipeline CI/CD yang gerbang deployment di sini turut menumpang di atasnya.

Jika di kemudian hari ditemukan bahwa hasil real-time API tidak konsisten dengan hasil batch untuk kasus yang sama (pelanggaran parity), atau model versi baru yang dipromosikan Orang #2 ternyata butuh fitur yang belum tersedia di skema request (pelanggaran Bagian 5.4 dokumen arsitektur soal kompatibilitas skema), titik ini perlu segera dikomunikasikan ke Orang #1 dan Orang #2 — bukan ditambal secara lokal di sisi real-time API saja, karena itu akan menciptakan sumber kebenaran kedua yang justru ingin dihindari sejak desain awal sistem ini.
