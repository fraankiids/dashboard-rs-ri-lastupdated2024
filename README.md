# Dashboard Rumah Sakit Indonesia

Dashboard interaktif berbasis **Streamlit** memakai `Hospital_Indonesia_datasets.csv`.

## Fitur
- **Peta choropleth nasional** — klik salah satu provinsi untuk otomatis memfilter
  seluruh dashboard (KPI, grafik, tabel) ke provinsi itu. Bisa ganti metrik peta:
  Jumlah RS / Total Tempat Tidur / Total Tenaga Kerja.
- **Kartu KPI**: total RS, total tempat tidur, total tenaga kerja, kepemilikan terbanyak
  (mengikuti scope nasional/provinsi yang aktif).
- **Rekap RS per Kelas** (donut), **per Kepemilikan** dan **per Jenis** (bar chart).
- **Daftar rumah sakit** dengan filter (kelas/jenis/kepemilikan) + pencarian nama/kab-kota.
- **Klik satu baris pada tabel** → langsung tampil **profil lengkap** rumah sakit tsb
  (alamat, jenis, kelas, kepemilikan, status BLU, tempat tidur, layanan, tenaga kerja).
  Kalau versi Streamlit belum mendukung klik-baris (`< 1.35`), tersedia juga
  dropdown pencarian RS manual sebagai cadangan.

> Catatan data: dataset sumber hanya berisi **angka total** per RS (bukan rincian per
> kelas kamar / jenis layanan / jenis tenaga kerja seperti pada contoh gambar referensi).
> Kalau kamu punya data rincian tsb, tab tambahan gampang ditambahkan di bagian
> "PROFIL RUMAH SAKIT TERPILIH" pada `app.py`.

## Cara Menjalankan (Lokal — direkomendasikan)
```bash
pip install -r requirements.txt
streamlit run app.py
```
Pastikan `Hospital_Indonesia_datasets.csv` ada di folder yang sama dengan `app.py`
(sudah disertakan). Peta butuh koneksi internet sekali untuk mengunduh batas wilayah
provinsi (GeoJSON) — kalau offline, peta otomatis diganti grafik batang per provinsi.

## Cara Menjalankan di Google Colab
Streamlit bukan notebook-native, jadi di Colab dijalankan lewat tunnel:

```python
!pip install -q streamlit streamlit-folium folium plotly branca requests

# upload app.py & Hospital_Indonesia_datasets.csv ke Colab dulu (folder yang sama), lalu:
!streamlit run app.py --server.port 8501 &>/content/log.txt &
!npx --yes localtunnel --port 8501
```
Jalankan cell, lalu klik link yang muncul dari `localtunnel` (masukkan IP yang ditampilkan
sebelumnya sebagai "Tunnel Password" jika diminta — dapatkan lewat
`!curl -s https://loca.lt/mytunnelpassword`).

## Struktur file
```
app.py                              # kode dashboard
Hospital_Indonesia_datasets.csv     # data
requirements.txt
README.md
```
