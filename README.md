# Emiten Intelligence — Live, tanpa SQL

Aplikasi **Streamlit** untuk mengambil berita emiten dari tautan sumber nasional/internasional,
melihat sentimen, dampak berita, rating, risiko, pergerakan saham, dan laporan riset.
**Tidak menggunakan database/SQLite untuk berita dan tidak menulis data/setting pengguna secara otomatis ke hard disk.
Pengecualian: jika memakai AI lokal, bobot model diunduh ke cache Hugging Face di runtime.**

## Versi 4 — Siap deploy Streamlit (11 November 2026)

- **Berita live tanpa histori permanen:** sumber RSS/tautan diambil saat Refresh. Berita,
  hasil analisis, dan hasil pemeriksaan rating hanya berada di memori sesi Streamlit.
  Tidak memakai SQL/SQLite. Cache model Hugging Face adalah pengecualian teknis,
  yaitu file bobot AI, **bukan** database berita.
- **IndoBERT + FinBERT on-demand:** saat memilih mesin lokal, default IndoBERT yang
  lebih ringan (~475 MB) disiapkan otomatis; FinBERT (~438 MB) hanya diunduh saat
  terdapat berita bahasa Inggris. Varian IndoBERT Large (~1,34 GB) tetap tersedia
  khusus mesin dengan RAM mencukupi. Model yang dimuat disimpan di cache satu model
  per proses sehingga pergantian emiten tidak menyebabkan unduhan ulang (selama
  cache runtime tersedia). Beralih bahasa dapat memerlukan pemuatan model lain.
- **Market Analytics → Pengaruh Berita terhadap Rating Kredit Perusahaan:** pilihan
  30 hari / 90 hari / 1 tahun. Tekan *Cari berita & aksi rating* untuk mengambil
  berita relevan periode tersebut dan riwayat rilis resmi PEFINDO secara on-demand.
  Tabel mencantumkan judul, tanggal, jenis hubungan (*Langsung*, *Entitas terkait*,
  *Tidak langsung*), kategori, arah indikasi, alasan, dan tautan berita.
- **Penilaian rating berlapis:** perubahan peringkat terkonfirmasi, perubahan
  outlook/CreditWatch terkonfirmasi, afirmasi/rating baru, dan indikasi material
  yang belum terbukti mengubah rating **dipisahkan**. Rating instrumen tidak
  disamakan dengan rating perusahaan. Berita negatif biasa tidak dianggap
  menyebabkan downgrade rating. Jika tidak ditemukan, pesan menyatakan
  *tidak ditemukan dari sumber yang berhasil diperiksa*, bukan kepastian absolut.
- **Pencarian 1 tahun bukan histori tersimpan:** pencarian sumber berita mempunyai
  batas cakupan/hasil dari masing-masing sumber; bila sumber gagal/belum dapat
  diakses, aplikasi menyampaikan keterbatasan tersebut.
- **Overview tetap 20 berita per halaman**, lengkap dengan navigasi dan hitungan
  total artikel yang terkumpul, dengan penyaringan relevansi per emiten.

Lihat **DEPLOY_STREAMLIT.md** untuk petunjuk unggah dan pengujian setelah deploy.

## Yang berubah di versi ini

- **Tab Laporan Keuangan dihapus**, termasuk ekstraksi laporan keuangan Excel/XBRL/PDF dan histori rasionya.
  Pembahasan berita *kinerja keuangan* tetap ada di News Intelligence.
- **Warna biru** pada label dampak = pemberitaan diperkirakan **menguntungkan emiten**;
  **merah** = diperkirakan **merugikan emiten**; warna netral = campuran/belum pasti.
  Ini **bukan** angka laba bersih atau rugi aktual dari laporan keuangan, juga bukan sinyal beli/jual.
- Artikel, hasil sentimen, rating, watchlist, pengaturan, peringatan dashboard, dan label evaluasi disimpan
  **sementara di memori per sesi**. Ketika sesi browser berakhir, data itu dapat hilang.
- Semua berita masih diambil melalui sumber publik (RSS/API/tautan), bukan dari file database.
- Laporan PDF/Excel dan ekspor CSV tetap bisa diunduh secara manual.
- **Skrip pembaruan di latar belakang dihapus**, karena tanpa penyimpanan tidak ada riwayat lintas sesi.
  Opsi *Auto* di sidebar hanya menyegarkan saat sesi browser masih terbuka.

## Menjalankan di komputer

Windows: ekstrak ZIP, buka folder `sentimen_emiten_app`, lalu klik `jalankan.bat`.
Skrip ini memasang dependensi lalu membuka browser secara otomatis.

Atau lewat terminal VS Code:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Python 3.10+ disarankan. Internet diperlukan untuk sumber live. Gunakan **Demo** untuk mencoba
fitur dengan data buatan tanpa membutuhkan koneksi berita.

## Deploy GitHub + Streamlit Community Cloud

Unggah **isi folder `sentimen_emiten_app`** (bukan ZIP-nya) ke root repository GitHub.
Buka Streamlit Community Cloud, pilih repo, lalu isi **Main file path**: `app.py`.
Tidak perlu konfigurasi SQL atau database.

### Struktur utama

```text
sentimen_emiten_app/
  app.py                 # Dashboard utama
  core/                  # Kolektor berita, analisis, rating, risiko, katalog
    session_store.py     # Penyimpanan hanya di memori sesi (Pandas)
    katalog_emiten.csv   # Katalog awal emiten BEI (dibaca, tidak diubah otomatis)
  .streamlit/config.toml
  requirements.txt
  requirements-ai.txt    # Kompatibilitas; dependensi AI kini di requirements.txt
  jalankan.py
  jalankan.bat
  jalankan.sh
  tests/
  README.md
```

## Alur penggunaan

1. Pilih emiten/kode saham (tersedia katalog BEI dan daftar counterparty).
2. Atur jangka waktu, klik **Refresh** untuk mengambil berita dari situs dan feed.
3. Di **Overview**, periksa skor sentimen, arah dampak (biru/merah), tingkat risiko,
   **sumber berita asli**, dan status verifikasi.
4. **News Intelligence**: filter berita dan lihat kenapa berita dikaitkan ke emiten.
5. **Global Impact**: informasi faktor komoditas/makro yang mungkin berpengaruh.
6. **Market Analytics**: lihat harga, return, reaksi historis, pembanding IHSG.
7. **Watchlist & Reports**: pantau beberapa emiten (dalam sesi) dan unduh hasil riset.
8. **Ask AI**: tanpa kunci API tersedia pencarian jawaban lokal dari berita yang terkumpul;
   narasi Claude memerlukan key pengguna sendiri dan biaya penyedia dapat berlaku.

## Batasan yang penting

- Katalog bawaan adalah **snapshot**, bukan daftar IPO/delisting real-time. Perbarui katalog
  saat sesi melalui file IDX jika ada perubahan; pembaruan tidak disimpan permanen.
- Skor berasal dari judul/ringkasan/metadata yang berhasil diambil. Artikel berbayar,
  pemblokiran akses otomatis, pencarian yang kurang tepat dan berita palsu memengaruhi hasil.
- GDELT dan sebagian layanan memiliki batas cakupan atau periode; label sentimen otomatis
  bersifat estimasi. Lakukan pengecekan ke tautan sumber resmi sebelum mengambil keputusan.
- Tidak ada penyimpanan otomatis setelah browser ditutup/di-refresh dengan sesi baru.
- Aplikasi ini bukan sistem audit laba-rugi dan bukan rekomendasi investasi.

## Tes

```bash
python -m pytest -q
```

Tes memeriksa aturan analisis & operasi data sementara; fungsi pengambilan berita dapat diuji
menggunakan respons tiruan. Runtime browser penuh tetap perlu dicoba dengan dependensi terpasang.

## Pemeriksaan relevansi berita (perbaikan 11 November 2026)

- Pencarian Google/Bing/RSS adalah **sumber calon artikel**, bukan bukti keterkaitan perusahaan.
- Mode Live memakai pencocokan ketat: judul/ringkasan/isi yang tersedia perlu menyebut nama/kode emiten atau entitas terkait, atau merupakan dokumen resmi yang spesifik terhadap emiten.
- Berita yang cuma muncul di hasil pencarian tanpa kaitan (sebelumnya label `Pencarian`) tidak ikut disimpan/ditampilkan pada analisis utama, skor, alert, atau reaksi harga.
- Label *sentimen teks* (misalnya rugi perusahaan lain) tidak otomatis berarti *dampak* ke emiten terpilih. Faktor makro/sektoral yang dipetakan ada di tab **Global Impact**.
- Informasi hubungan sebenarnya tetap terbatas pada judul/ringkasan/metadata yang bisa diambil; aplikasi ini bukan pembuktian kausal atau rekomendasi beli/jual.
- Bila masih muncul hasil lama dalam tab browser Streamlit yang terbuka saat deploy, restart sesi lalu **Refresh** emiten.

## Update — IndoBERT + FinBERT otomatis, 20 berita per halaman, relevansi BBCA

**Model lokal.** `torch`, `transformers`, dan `huggingface-hub` kini tercantum dalam
`requirements.txt`, sehingga dependensinya dipasang saat instalasi/deploy. Saat opsi
**IndoBERT + FinBERT** dipilih, aplikasi mengunduh IndoBERT saja secara otomatis
(di mode hemat RAM), dan FinBERT hanya ketika artikel bahasa Inggris dianalisis.
Pemuatan model di RAM juga terjadi secara bertahap, tidak sekaligus. Tidak perlu Claude API key dan tidak ada biaya permintaan AI.
Unduhan bobot model dan waktu inferensi cukup besar (IndoBERT Large ~335 juta parameter,
FinBERT ~110 juta parameter). Jika ruang disk/RAM/jaringan tidak mencukupi, aplikasi
menampilkan peringatan dan menggunakan kamus sebagai fallback. Pada hosting yang
menghapus cache ketika restart, model dapat terunduh lagi. Bobot disimpan di cache
Hugging Face lokal milik runtime, **bukan di database aplikasi** dan **bukan di GitHub**.
Model hanya memberi klasifikasi sentimen teks; relevansi perusahaan tetap diperiksa
sebelumnya. Periksa lisensi model sebelum pemakaian komersial.

**Overview.** Panel kanan kini menampilkan **20 artikel terbaru** (bukan hanya
8 peristiwa unik), diurutkan dari paling baru. Di bawahnya tertera
"Menampilkan 1–20 dari N berita relevan" dan pilihan **Sebelumnya / Berikutnya / Buka halaman**.
Contoh 1.760 adalah ilustrasi, **bukan jumlah berita yang dijanjikan**;
jumlah sebenarnya mengikuti berita yang tersedia dari RSS/API dan berhasil disaring.
Tab News Intelligence > Semua artikel juga dipaginasi 20 per halaman.

**Relasi BBCA.** Hubungan langsung harus menyebut BBCA, Bank Central Asia, atau BCA;
berita tentang **BCA Digital, BCA Syariah, BCA Finance**, dan pemegang kendali
**Dwimuria Investama Andalan** dapat menjadi "Entitas terkait". Berita umum
Djarum/Blibli/SoftBank tidak lagi diambil sebagai berita BBCA hanya karena berada di
satu grup besar atau muncul pada hasil kueri. Artikel makro seperti **BI Rate,
The Fed, rupiah, pertumbuhan kredit, inflasi Indonesia, aturan OJK sektor bank**
hanya masuk kategori **Tidak langsung** jika topiknya benar-benar disebut dalam
judul/ringkasan dan sesuai pemetaan sensitivitas sektor. Hubungan tidak langsung
menunjukkan **potensi jalur pengaruh**, bukan estimasi kausal ke laba atau harga BBCA.

**Perbarui di GitHub.** Ganti kode lama dengan isi ZIP ini di root repositori,
biarkan Streamlit memasang requirements yang baru, lalu **Refresh** emiten BBCA.
Sesi Streamlit lama yang menyimpan berita salah dapat direset lewat restart browser.


## V5 — Grup korporasi dan rating PEFINDO/Fitch (11 November 2026)

- **Grup di sebelah emiten:** pada dropdown emiten muncul contoh `INKP · ... · Sinarmas Group`,
  `BMRI · ... · Mandiri Group`, `BBCA · ... · Djarum Group`. Detail grup + sumber ditampilkan
  langsung di bawah pemilih. Referensi utama adalah `data/grup_excel.csv` yang diekstrak
  dari workbook Limit Counterparty pengguna: tab *Perbankan*, *Non Perbankan*, *Group*.
- **Emiten lain:** jika tidak ada dalam daftar Excel, gunakan kolom `Grup` pada katalog
  `core/katalog_emiten.csv` dengan informasi asal; jika juga tidak ada, tampil
  `Belum teridentifikasi`. Grup dapat diubah sementara di Pengaturan → Grup perusahaan.
  Grup tidak menjadi alias pencarian berita, agar berita lain dari satu holding tidak
  otomatis dinyatakan relevan untuk saham yang dipilih.
- **Tidak ada Telegram / Gmail / SMTP** di Pengaturan. Peringatan risiko tetap
  tersedia pada dashboard, tanpa pengiriman keluar. Kolom email kontak SEC EDGAR
  adalah identitas wajib untuk permintaan SEC, bukan fitur notifikasi.
- **Rating:** panel Market Analytics memungkinkan pencarian PEFINDO, Fitch, atau keduanya.
  Pengaturan → Rating tetap menyediakan sinkron massal PEFINDO dan tombol pencarian Fitch
  untuk emiten terpilih. Fitch menggunakan pencarian publik terarah; hanya rilis bertautan
  `https://fitchratings.com/...` yang menyebut issuer secara jelas dan mempunyai tanggal
  teridentifikasi yang dapat diklasifikasikan sebagai pengumuman resmi. Keterbatasan
  indeks, paywall, dan pembatasan akses bisa menyebabkan hasil tidak lengkap.
- Peringkat **issuer/kredit** berbeda dengan rating **obligasi spesifik**, dan tidak
  boleh disamakan dengan sentimen harga saham. Ketidaktersediaan data bukan bukti
  perusahaan tidak memiliki rating.
- File `data/grup_excel.csv` adalah **referensi statis paket**, bukan database berita
  atau histori perusahaan. Berita, rating temuan, dan perubahan grup pengguna
  hanya berada di memori sesi.
