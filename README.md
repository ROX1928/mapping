# Peta Toko Motorola

Aplikasi Streamlit untuk melihat lokasi toko per area, mencari toko, membuka
navigasi Google Maps, dan mengunduh daftar toko sebagai CSV.

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
4. Pilih **Deploy**. Aplikasi memakai CARTO Voyager tanpa API key secara
   default.

Google Maps Tiles bersifat opsional. Untuk mengaktifkannya, tambahkan
`GOOGLE_MAPS_API_KEY` melalui pengaturan **Secrets** aplikasi di Streamlit
Community Cloud, bukan ke file kode atau repositori.

> Repositori publik membuat file Excel dan informasi lokasi toko yang
> disertakan dapat dilihat siapa saja.
