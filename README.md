# Aplikasi Uji Keamanan dan Pemulihan PIN Arsip

Repositori ini berisi aplikasi desktop untuk menguji ketahanan PIN atau sandi numerik pada file arsip terenkripsi menggunakan pendekatan dictionary attack dan brute force. Setelah proses pengujian, aplikasi dapat membantu mengekstrak file, membuat laporan hasil, serta mengamankan ulang file menggunakan sandi baru yang lebih kuat.

## Judul Tugas Akhir

**Rancang Bangun Aplikasi untuk Uji Pemulihan PIN atau Sandi Numerik pada File Arsip Terenkripsi Menggunakan Algoritma Brute Force**

## Fitur Utama

- Pengujian PIN 4 digit dan 6 digit.
- Dukungan pengujian file ZIP, RAR, 7Z, dan PDF.
- Tahap awal menggunakan kamus PIN umum, kemudian dilanjutkan dengan brute force numerik.
- Pemrosesan beberapa file dan pemantauan progres melalui antarmuka desktop.
- Pencatatan hasil pengujian pada database SQLite lokal.
- Pembuatan laporan hasil, frekuensi PIN, dan kinerja perangkat.
- Ekstraksi file setelah PIN ditemukan.
- Pembuatan sandi baru yang lebih kuat dan pengamanan ulang file.

## Struktur Repositori

```text
.
├── asset/img/logo.png          # Logo aplikasi
├── database/pin_dictionary.db  # Kamus PIN dan database log yang sudah dikosongkan
├── main.py                     # Source code utama
├── main.spec                   # Konfigurasi build PyInstaller
├── requirements.txt            # Dependensi Python
└── DISCLAIMER.md               # Ketentuan penggunaan
```

Folder hasil build, shortcut Windows, dan riwayat pengujian pribadi tidak disertakan agar repositori tetap bersih dan aman.

## Instalasi

Disarankan menggunakan Windows dan Python versi yang masih didukung.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Untuk dukungan RAR, pastikan utilitas RAR/UnRAR tersedia dan dapat dipanggil dari sistem.

## Membuat File EXE

```bash
pip install pyinstaller
pyinstaller --clean main.spec
```

Hasil build akan tersedia pada folder `dist`. File EXE tidak disimpan langsung di source repository dan dapat diterbitkan secara terpisah melalui GitHub Releases.

## Catatan Keamanan

Aplikasi ini dibuat untuk tujuan akademik, pemulihan akses, dan pengujian keamanan pada file milik sendiri atau file yang telah memperoleh izin pengujian. Lihat [DISCLAIMER.md](DISCLAIMER.md) sebelum menggunakan aplikasi.

## Pemilik

**Chidir Zain Albukhori**
