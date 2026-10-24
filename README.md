# Peta Toko Motorola

Aplikasi Streamlit untuk melihat lokasi toko per area dengan lingkaran sektor,
jalur kunjungan mengikuti jalan, jarak berkendara antar toko berurutan, label
nama toko yang menyesuaikan posisi agar tidak bertumpuk, pencarian, navigasi
Google Maps, jarak km yang tampil langsung di setiap segmen jalur, lingkaran
sektor yang diperbesar agar terlihat saat zoom jauh dan kembali ke radius
sebenarnya saat zoom dekat, unduhan CSV, serta screenshot PNG per area dan
sektor yang dapat diunduh sebagai ZIP.

Screenshot menampilkan basemap jalan, nomor dan daftar nama toko, rute, serta
jarak berkendara dari toko sebelumnya. Peta dibuat saat tombol screenshot
ditekan dan memerlukan koneksi ke layanan tile OpenStreetMap dan OSRM.

Excel detail dapat diunduh dari bagian **Screenshot detail per area dan
sektor**. Workbook berisi lembar ringkasan, lembar rute per area, dan lembar
rute per kecamatan, dengan urutan kunjungan, jarak berkendara antar toko,
alamat, koordinat, dan tautan navigasi.
Jarak pada area/sektor dengan satu toko dibiarkan kosong dan diberi keterangan
bahwa tidak ada rute antar toko; jarak lain ditampilkan hingga tiga angka desimal
agar perjalanan pendek tidak terlihat sebagai 0 km. File unduhan terbaru bernama
`detail_toko_per_area_dan_sektor_revisi3.xlsx`. Ringkasan area juga menampilkan
daftar kecamatan dan nama toko yang dikelompokkan menurut kecamatan.

Pembagian sektor: A1 Purwakarta, A2 Karawang Timur, A3 Karawang Kota,
A4 Pantura Cilamaya-Pamanukan, dan A5 Subang Kota.

## Jalankan lokal

```bash
pip install -r requirements.txt
streamlit run app_peta_toko.py
```

File `Daftar_Toko_Motorola_Fixed.xlsx` harus berada di folder yang sama dengan
aplikasi. Jika file tidak disertakan, pengguna dapat mengunggah file `.xlsx`
melalui sidebar.

## Deploy ke Streamlit Community Cloud

1. Push `app_peta_toko.py`, `requirements.txt`, dan
   `Daftar_Toko_Motorola_Fixed.xlsx` ke repositori GitHub.
2. Masuk ke [share.streamlit.io](https://share.streamlit.io/) dan pilih
   **Create app**.
3. Pilih repositori, branch, dan `app_peta_toko.py` sebagai main file.
4. Pilih **Deploy**. Tanpa key, aplikasi memakai tile OpenStreetMap. Untuk
   memakai CARTO Voyager, tambahkan `CARTO_API_KEY` melalui **App settings >
   Secrets** di Streamlit Community Cloud:

   ```toml
   CARTO_API_KEY = "your-restricted-carto-key"
   ```

   Atribusi basemap ditampilkan pada peta. Penggunaan tile OpenStreetMap
   mengikuti [Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/).

Google Maps Tiles bersifat opsional. Untuk mengaktifkannya, tambahkan
`GOOGLE_MAPS_API_KEY` melalui pengaturan **Secrets** aplikasi di Streamlit
Community Cloud, bukan ke file kode atau repositori.

Batasi API key CARTO dan Google untuk domain aplikasi yang digunakan. Jangan
memasukkan key ke source code, file Excel, atau repositori.

> Repositori publik membuat file Excel dan informasi lokasi toko yang
> disertakan dapat dilihat siapa saja.
