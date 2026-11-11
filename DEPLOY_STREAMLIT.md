# Deploy Emiten Intelligence V5 ke Streamlit Community Cloud

## 1. Unggah ke GitHub

1. Ekstrak ZIP dan buka folder `sentimen_emiten_app`.
2. Unggah **isi** folder tersebut ke root repository GitHub (bukan ZIP/folder pembungkus).
3. Pastikan `app.py`, `requirements.txt`, folder `core`, `.streamlit/config.toml`, `data/grup_excel.csv`, dan `tests` ada.
4. Jangan unggah file `.env`, API key pribadi, cache model, atau database lama.

## 2. Streamlit Community Cloud

1. Klik **New app** dan pilih repo/branch GitHub.
2. Masukkan `app.py` di **Main file path** dan deploy.
3. Tunggu instalasi paket yang diperlukan. `torch` dan `transformers` membutuhkan resource relatif besar.
4. Pada sidebar pilih mode **Live**, lalu emiten (BBCA/BMRI dll.).
5. Pilih mesin **Kamus keuangan** dulu untuk uji Refresh berita tanpa pengunduhan model.
6. Setelah berita berhasil, coba **IndoBERT + FinBERT → Hemat RAM**.
   IndoBERT diunduh otomatis ke cache server saat dipilih dan FinBERT saat memproses teks Inggris.
7. Buka **Market Analytics → Pengaruh Berita terhadap Rating Kredit Perusahaan**, pilih 30 hari
   atau 1 tahun, atur sumber PEFINDO/Fitch, lalu klik **Cari berita & aksi rating**.

## 3. Cara membaca panel rating

- **Upgrade/downgrade resmi:** aksi yang terkonfirmasi pada rilis lembaga pemeringkat;
  **perusahaan** berbeda dengan rating obligasi/sukuk tertentu.
- **Outlook/CreditWatch resmi:** perubahan status/peninjauan; belum tentu menaikkan atau menurunkan rating.
- **Berita indikasi rating:** indikator risiko kredit (misalnya gagal bayar/likuiditas)
  atau berita lembaga yang belum terverifikasi; **bukan** bukti rating telah berubah.
- **Afirmasi:** rating dinyatakan tetap. Perhatikan tanggal dan lembaganya.
- Setiap berita menampilkan **Hubungan: Langsung / Entitas terkait / Tidak langsung** dan link asli.
- **Tidak ditemukan** berarti tidak ditemukan **dalam sumber yang berhasil diperiksa**;
  bukan jaminan peringkat perusahaan tidak berubah di semua lembaga.

## 4. Batasan penyimpanan dan RAM

- Tidak ada database historis otomatis; berita dan hasil rating tersimpan sementara dalam `st.session_state`.
- Cache model HF tetap menggunakan ruang disk. Jika server restart dan cache dihapus,
  model dapat diunduh ulang. Cache model bukan histori berita.
- Pada paket gratis RAM dan CPU tidak dijamin; jika bermasalah, gunakan **Kamus keuangan**.
- Gunakan varian **IndoBERT Besar** hanya bila hosting memiliki RAM memadai.
- Jangan memasukkan API key ke repository publik. Pengaturan Claude menggunakan key terpisah.
- Penggunaan FinBERT harus memperhatikan ketentuan lisensi bobot model dari pengembang.

## 5. Uji setelah deploy

1. **BBCA:** berita SoftBank/Blibli yang tidak berkaitan tidak boleh masuk hasil analisis BBCA.
2. **BMRI:** berita langsung BMRI/Bank Mandiri dan entitas terkait terpilih dapat masuk;
   berita perusahaan lain tanpa bukti keterkaitan ditolak.
3. **Overview:** 20 berita per halaman, jumlah total sesuai berita yang berhasil dikumpulkan.
4. **Rating 30 hari:** bila tidak ada aksi resmi dari sumber yang terjangkau, tampil pesan
   tidak ditemukan; berita indikasi dipisah dari rating aktual.
5. **Rating 1 tahun:** klik pemeriksaan terpisah; judul, tanggal, hubungan, dan link
   sumber yang terjangkau ditampilkan.
6. **IndoBERT/FinBERT:** perhatikan label mesin artikel; jika gagal unduh/model,
   aplikasi mungkin memakai fallback kamus, bukan berarti AI lokal berhasil aktif.

## 6. Tes lokal

```bash
python -m pip install -r requirements.txt
python -m pytest -q
streamlit run app.py
```

Pengujian yang memerlukan internet atau UI browser tidak digantikan oleh tes unit.


## 7. Fitur V5: Grup perusahaan dan Fitch

1. Saat memilih `INKP`, cek grup `Sinarmas Group`; BMRI → Mandiri Group, BBCA → Djarum Group.
2. Jika grup tidak sesuai, gunakan **Pengaturan → Grup perusahaan** untuk mengubah
   nilai sementara (tanpa file/database permanen).
3. Cek **Market Analytics → Rating** dan pilih sumber PEFINDO, Fitch, atau keduanya.
4. Fitch memakai indeks pencarian publik menuju rilis resmi (bukan API berbayar).
   Sebagian rilis mungkin tidak terindeks atau memerlukan login; gunakan tautan
   **Fitch Latest Rating Actions** untuk verifikasi manual. Jangan tafsirkan hasil kosong
   sebagai bukti rating tidak tersedia.
5. Tab Notifikasi, konfigurasi SMTP, dan konfigurasi Telegram sudah dihapus.
6. Penting: `.gitignore` harus mengizinkan `data/grup_excel.csv`, karena tanpanya
   label grup Excel gagal dimuat saat deploy.
