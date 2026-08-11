# Report — Milestone 1.3: Skema dan Validasi Data Input

## Ringkasan

Milestone 1.3 selesai. Dua kontrak skema eksplisit sudah dibangun: `churn_prediction.schema.raw_schema.RawDataSchema` (pandera, jalur batch) dan `churn_prediction.schema.request_schema.ChurnPredictionRequest` (Pydantic, jalur real-time) — keduanya dibangun terprogram dari satu sumber constraint (`schema/constants.py`), bukan didefinisikan independen dua kali. 102 test lulus di seluruh repo (33 baru untuk Milestone 1.3), termasuk uji konsistensi behavioral yang menemukan dan memperbaiki satu inkonsistensi nyata antara kedua skema.

Empat keputusan genuinely-terbuka (target tabel skema, library batch, library real-time, konvensi field) diklarifikasi ke user sebelum plan ditulis — bukan diasumsikan.

## Kontrak Sumber vs Bukti (KK1-KK2)

| KK | Kriteria | Bukti |
|---|---|---|
| **KK1** | Data yang melanggar skema (kolom hilang, tipe salah, nilai di luar rentang wajar) ditolak dengan pesan jelas menyebutkan bagian mana yang tidak valid. | `tests/schema/test_raw_schema.py` (8 test: 1 valid + 7 pelanggaran — kolom hilang, tipe salah, `tenure` di luar [1,72], `monthly_charges` negatif, `senior_citizen` di luar {0,1}, kategori tak dikenal) dan `tests/schema/test_request_schema.py` (8 test paralel, kasus sama) — seluruh kasus pelanggaran menghasilkan `pandera.errors.SchemaError`/`SchemaErrors` atau `pydantic.ValidationError` yang pesannya memuat nama kolom/field yang salah (`pytest.raises(..., match=<nama kolom>)`). |
| **KK2** | Skema request API dan skema data mentah, dibandingkan berdampingan, menunjukkan pemetaan konsisten — tidak ada field/kolom bermakna sama tapi didefinisikan beda. | `tests/schema/test_schema_consistency.py` (40 test behavioral: field set identik, tiap dari 16 kolom kategorikal diuji nilai valid+invalid sama di kedua skema, tiap dari 3 kolom numerik diuji batas rentang sama) — **menemukan 1 inkonsistensi nyata** (`total_charges=0` diterima Pydantic tapi ditolak pandera karena dtype ketat), diperbaiki (`coerce=True`), lalu 40/40 lulus. Dokumentasi pemetaan 19 field->kolom->tipe->constraint di `schema/__init__.py` (identity mapping, tetap didokumentasikan penuh, bukan diasumsikan trivial). |

## Keputusan Final

Lihat [`decisions.md`](./decisions.md) — 4 keputusan: (1) constraint bersumber dari audit M1.1 (bukan didesain ulang), (2) satu sumber constraint dipakai dua skema, (3) pandera/pydantic dipin langsung (bukan provisional seperti dependency M1.2), (4) skema request hanya 19 field fitur, tanpa ID/correlation field. Empat klarifikasi genuinely-terbuka (target tabel, library batch, library real-time, konvensi field) dijawab user sebelum plan ditulis — dicantumkan di `decisions.md`.

## Perubahan dari Plan Awal

- Tidak ada revisi besar terhadap plan seperti Milestone 1.2 — plan disusun setelah 4 klarifikasi dijawab lebih dulu, jadi tidak ada asumsi yang perlu dikoreksi di tengah eksekusi.
- **Temuan nyata saat Checkpoint 4** (bukan penyimpangan proses, tapi hasil kerja test yang memang dirancang untuk menemukan ini): `raw_schema.py` awalnya `coerce=False` untuk semua kolom, menyebabkan `total_charges=0` (int, hasil inferensi dtype pandas pada DataFrame satu-baris) ditolak murni karena dtype, padahal nilainya valid secara semantik dan Pydantic menerimanya (auto-coerce). Diperbaiki dengan `coerce=True` khusus kolom numerik. `test_wrong_type_rejected` di `test_raw_schema.py` disesuaikan menerima dua kelas exception pandera (`SchemaError`/`SchemaErrors`, keduanya bentuk penolakan sah, hanya beda jalur — value-check vs coercion-failure).

## Keterbatasan dan Item Terbuka

- **`telco_customers_synthetic` masih 0 baris** — Checkpoint 5 (verifikasi terhadap data real) memakai `telco_customers_source` (PascalCase, di-rename) sebagai proxy, sama seperti pola Milestone 1.2. Skema belum pernah diuji terhadap baris asli dari tabel `telco_customers_synthetic` sungguhan (constraint DB-nya sudah dicek konsisten di Milestone 1.1 Bagian H.3, tapi belum ada baris nyata untuk validasi end-to-end terhadap tabel itu sendiri).
- **KT-1 (Milestone 1.6 formal)** — kontrak skema data mentah sudah dipakai konsisten dua milestone berturut (1.2, 1.3), tapi kesepakatan formal dengan "pemilik sumber data" (jalur komunikasi perubahan skema ke depan) belum dilakukan sebagai milestone tersendiri.
- **KT-2, sisa KT-3** — tidak terpengaruh/tidak berubah oleh milestone ini.
- **Skema request real-time belum diintegrasikan ke endpoint sungguhan** — itu wewenang Milestone 3.2. `request_schema.py` di milestone ini murni definisi kontrak+validasi, belum ada FastAPI/server yang memanggilnya.

## Follow-up

- Siap dibagikan ke Orang #2 (kontrak `raw_schema.py` untuk gerbang kualitas data batch, Milestone 2.4) dan Orang #3 (kontrak `request_schema.py` untuk endpoint real-time, Milestone 3.2) — sesuai tujuan eksplisit KK milestone ini.
- Saat Milestone 1.5 (inference service package) dibangun, `raw_schema.py`/`request_schema.py` seharusnya dipanggil sebagai gerbang validasi SEBELUM data masuk ke `churn_prediction.transform.PreprocessingPipeline` — belum diverifikasi integrasinya (di luar cakupan M1.3, tapi dicatat sebagai titik sambung berikutnya).
- KT-1 (Milestone 1.6), KT-2, sisa KT-3 tetap perlu ditutup — lihat `docs/keputusan-tertunda.md`.
