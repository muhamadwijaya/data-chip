# GTInk - Alat Chip Kartrid EAJet / GT1000

GTInk adalah alat berbasis Python untuk membaca, menganalisis, mengedit, dan
mengkloning chip MIFARE Classic 1K yang dipakai kartrid tinta EAJet/GT1000.
Semua logika inti memakai pustaka standar Python; Tkinter dipakai untuk GUI.

> **Status pengujian:** clone `1EB75C2C_full_65000.bin` sudah ditulis ke kartu
> magic Gen1a dan dibaca ulang 64 blok sama persis. Pada 2026-10-26, emulator
> ISO14443-4 (Proxmark3) dengan replay challenge set C diterima printer:
> `Cek berhasil / printer siap`. Kunci DES tidak perlu diketahui; cukup
> replay GET CHALLENGE yang cocok dengan response MAC.

---

## 1. Ringkasan temuan data

Ada empat dump sumber:

| UID | Counter | Hex | Fill tail | Keterangan |
|---|---:|---:|---|---|
| `1EB75C2C` | 64016 | `0xFA10` | `FF` | chip penuh |
| `5EEFAB9B` | 64606 | `0xFC5E` | `FF` | chip penuh |
| `BE8AAA9B` | 12107 | `0x2F4B` | `00` | chip low-ink |
| `FE7EA17E` | 64516 | `0xFC04` | `FF` | chip penuh |

Struktur satu kartu:

- 16 sektor, 64 blok, 1024 byte.
- Key A/B default `FFFFFFFFFFFF`, access bits `FF078069`, GPB `69`.
- Dua record: blok **4..32** dan **33..61**.
- Tiap record: 29 blok fisik, 7 blok trailer, 22 blok data = 352 byte.
- 12 blok pertama = **payload 192 byte** (berisi data kartrid, unik per chip).
- 10 blok berikutnya = **tail 160 byte** (sebagian besar pola fill).
- Payload record 1 dan record 2 selalu sama; tail juga sama.
- Counter ada di **blok 29 dan 58, offset 10, 16-bit little-endian**.
- Counter kedua record selalu sama pada keempat dump.
- Chip penuh memakai fill `FF`; chip low-ink memakai fill `00`.
- Nominal penuh yang paling mungkin: **65000** (`0xFDE8`); maksimum 16-bit
  adalah **65535** (`0xFFFF`).
- Tidak ditemukan checksum, CRC, hash, atau signature yang menghubungkan
  counter ke payload. Pada sesama chip penuh, tail hanya berbeda di dua byte
  counter.

Interpretasi counter sebagai **sisa tinta** didukung oleh:

- chip penuh: 64016-64606;
- chip low-ink: 12107;
- `LOW_INK_THRESHOLD=15` dan `LOW_INK_THRESHOLD_UPVALUE=60` di `SysParam.ini`;
- `12107 / 65000` sekitar 18,6%, dekat dengan ambang low-ink.

---

## 2. Persyaratan

- Windows (diuji di Windows dengan Python 3.14).
- Python 3.10 atau lebih baru, dengan Tkinter.
- Proxmark3 hanya diperlukan untuk baca/tulis kartu fisik.
- Client Proxmark3 yang diuji:
  `C:\ProxSpace\pm3\proxmark3\client\proxmark3.exe`
- Folder `C:\ProxSpace\msys2\mingw64\bin` harus ada di `PATH` agar client
  tidak keluar diam-diam. GTInk menambahkannya otomatis saat memanggil client.

Tidak ada paket Python eksternal yang dibutuhkan.

---

## 3. Mulai cepat

### GUI

Klik dua kali:

```text
gtink_gui.cmd
```

Atau dari terminal:

```powershell
py gtink_gui.py
```

Tab yang tersedia:

1. **Dump & Analisis** - memuat keempat dump, tabel, rincian, laporan.
2. **Buat Clone** - memilih sumber, counter, fill, UID baru, backend script.
3. **Tulis / Verifikasi** - baca kartu, tulis clone, backup, verifikasi.
4. **Bantuan** - ringkasan temuan, urutan uji, dan peringatan.

### CLI

```powershell
py gtink.py --help
py gtink.py info --detail
py gtink.py analyze
py gtink.py selftest
```

Bisa juga memakai modul: `py -m gtink info`.

`gtink.cmd` adalah pembungkus CLI; tanpa argumen ia menampilkan bantuan. Jika
GUI tidak terbuka lewat `gtink_gui.cmd`, jalankan `py gtink_gui.py` dari
terminal untuk melihat pesan error.

---

## 4. Perintah CLI

### Melihat dump

```powershell
py gtink.py info
py gtink.py info --detail
py gtink.py info --json
py gtink.py analyze --output laporan.txt
```

### Membuat paket clone rekomendasi

```powershell
py gtink.py clone --recommended --out clones
```

Menghasilkan 11 clone:

- `1EB75C2C_exact_64016.bin` - kontrol persis.
- `1EB75C2C_full_65000.bin` - kandidat utama.
- `1EB75C2C_max_65535.bin` - cadangan maksimum.
- `1EB75C2C_full_65000_newuid_92A7CC05.bin` - UID baru.
- `5EEFAB9B_exact_64606.bin` dan `5EEFAB9B_full_65000.bin`.
- `FE7EA17E_exact_64516.bin` dan `FE7EA17E_full_65000.bin`.
- `BE8AAA9B_exact_12107.bin` - kontrol low-ink.
- `BE8AAA9B_full_65000_keep00.bin` - low-ink, fill `00`.
- `BE8AAA9B_full_65000_fillFF.bin` - low-ink dinormalisasi ke `FF`.

Setiap clone mendapat file `.bin`, `.json`, dan tiga script Proxmark3
(`gen1a`, `gen2`, `gen4`). Folder juga berisi `manifest.json` dan
`README_UJI.txt`.

### Clone tunggal

```powershell
py gtink.py clone `
  --source "tij gt1000 CHIP INK\hf-mf-1EB75C2C-dump.bin" `
  --counter 65000 `
  --out clones `
  --backend gen1a --backend gen2 --backend gen4
```

Pilihan lain:

```powershell
# UID baru deterministik dari payload
py gtink.py clone --source-uid 1EB75C2C --counter 65000 --random-uid --out clones

# UID baru manual
py gtink.py clone --source-uid 1EB75C2C --counter 65000 --new-uid A1B2C3D4 --out clones

# Normalisasi tail low-ink ke FF
py gtink.py clone --source-uid BE8AAA9B --counter 65000 --fill ff --out clones

# Ambil tail dari dump lain
py gtink.py clone --source-uid 1EB75C2C --counter 65000 --tail-from "tij gt1000 CHIP INK\hf-mf-5EEFAB9B-dump.bin" --out clones
```

### Membuat script dari BIN yang sudah ada

```powershell
py gtink.py scripts --file clones\1EB75C2C_full_65000.bin --out scripts
```

### Membaca kartu

```powershell
py gtink.py read --out readback.bin --port COM11
```

Hasil baca disimpan sebagai `.bin` dan `.json` (atau `.eml` bila ekstensi
output `.eml`). Gunakan `--keys` bila kartu tidak memakai key default.

### Menulis kartu

```powershell
py gtink.py write `
  --file "clones\1EB75C2C_full_65000.bin" `
  --backend gen1a `
  --port COM11 `
  --yes
```

Default:

- kartu dibaca dan dicadangkan ke `backups/` sebelum ditulis;
- setelah menulis, seluruh 64 blok dibaca ulang dan dibandingkan;
- `--no-backup` melewati backup;
- `--no-verify` melewati verifikasi;
- `--allow-invalid` mengizinkan clone dengan error validasi.

Kode keluar:

- `0` - berhasil dan (bila verifikasi aktif) cocok;
- `1` - kesalahan parameter/Proxmark3;
- `2` - tulis selesai tetapi verifikasi menemukan blok berbeda.

### Replay emulator ISO14443-4

Jalur printer yang sebenarnya adalah APDU ISO14443-4 (FM1208/FMCOS), bukan
MIFARE Classic. Perintah `replay` menampilkan state yang direkam dan perintah
`hf 14a simaid` untuk Proxmark3:

```powershell
py gtink.py replay --list
py gtink.py replay --set C
py gtink.py replay --set C --json
```

Firmware Proxmark3 harus di-build untuk set yang sama:

```powershell
py proxmark_patch\build_flash.py --set C --flash
py printer_test.py --set C --seconds 600
```

Set yang tersedia: `A`, `B`, `C`, dan `factory`. Set C sudah diuji dan
diterima printer (`Cek berhasil / printer siap`). Response MAC secure read
bergantung pada GET CHALLENGE, jadi challenge per set harus cocok:

| Set | Challenge 0006 | Challenge 0007 |
|---|---|---|
| A | `69 1D 4F C3` | `1A 6A CE 1F` |
| B | `96 BF 9A 55` | `87 7E 50 87` |
| C | `B9 BE 71 5F` | `A6 1D 5A 69` |
| factory | `B9 BE 71 5F` | `A6 1D 5A 69` |

---

## 5. Backend Proxmark3

### Gen1a (magic card biasa)

```text
hf mf cload -f "file.bin" --1k
```

Menulis seluruh 64 blok, termasuk blok 0/UID. Ini backend yang dipakai pada
kartu yang sudah diuji.

### Gen2 / CUID

Satu perintah per blok:

```text
hf mf wrbl --blk 1 -k FFFFFFFFFFFF -d <32 hex>
...
hf mf wrbl --blk 63 -k FFFFFFFFFFFF -d <32 hex>
hf mf wrbl --blk 0 -k FFFFFFFFFFFF -d <32 hex> --force
```

Blok 0 ditulis **terakhir** agar perubahan UID tidak mengganggu penulisan blok
lain. `--force` diperlukan untuk blok 0. Beberapa kartu CUID memakai perintah
khusus dan mungkin tidak menerima penulisan blok 0 dengan cara ini.

### Gen4 / Ultimate

```text
hf mf gload -f "file.bin" --1k
```

Kartu Gen4 harus dikonfigurasi sebagai MIFARE Classic 1K terlebih dahulu
(misalnya dengan `script run hf_mf_ultimatecard`).

### Menjalankan script

Script berisi satu perintah per baris dan komentar `#`. Contoh:

```powershell
cd clones\scripts
& "C:\ProxSpace\pm3\proxmark3\client\proxmark3.exe" -p COM11 -s "1EB75C2C_full_65000_gen1a.txt"
```

Atau buka client interaktif, lalu:

```text
script run 1EB75C2C_full_65000_gen1a.txt
```

Path di dalam script memakai path absolut dan tanda kutip bila mengandung
spasi, misalnya `"O:/tij gt 1000/clones/..."`.

---

## 6. Urutan pengujian di printer

Gunakan kartu magic yang sama, tulis satu file, pasang ke printer, catat pesan
yang muncul, lalu ulangi.

1. **`1EB75C2C_exact_64016.bin`** - kontrol.
   - Jika printer menolak exact, masalahnya bukan counter.
2. **`1EB75C2C_full_65000.bin`** - kandidat utama.
   - Kartu saat ini sudah berisi file ini dan sudah diverifikasi.
3. **`1EB75C2C_max_65535.bin`** - jika 65000 ditolak.
4. **`1EB75C2C_full_65000_newuid_92A7CC05.bin`** - jika printer menyimpan
   riwayat UID/counter dan menolak rollback.
5. **`5EEFAB9B_full_65000.bin`** dan **`FE7EA17E_full_65000.bin`** - sumber
   lain, jika payload/UID tertentu ditolak.
6. **`BE8AAA9B_full_65000_keep00.bin`** dan
   **`BE8AAA9B_full_65000_fillFF.bin`** - varian chip low-ink.

### Jalur ISO14443-4 (emulator Proxmark3)

Jalur ini yang dipakai printer sebenarnya dan **sudah terbukti diterima**
dengan set C. Urutannya:

```powershell
py proxmark_patch\build_flash.py --set C --flash
py printer_test.py --set C --seconds 600
```

Saat emulator berjalan, picu `Ink Box Check` di printer. Layar printer
menampilkan `Cek berhasil / printer siap` untuk set C.

Untuk set lain, ganti `C` dengan `A`, `B`, atau `FACTORY` pada **kedua**
perintah. Firmware dan `printer_test.py` wajib memakai set yang sama karena
challenge secure read berbeda. Setelah flash, COM11 bisa hilang sebentar;
cabut/colok ulang USB Proxmark3.

### Membaca hasilnya

- **Exact diterima, 65000 ditolak** → ada batas nominal, validasi counter,
  atau deteksi rollback. Coba 65535, lalu nilai asli dari dump lain.
- **Exact ditolak juga** → counter bukan penyebab utama. Kemungkinan kartu
  magic terdeteksi, UID terikat ke payload/signature, atau printer memakai
  pemeriksaan lain.
- **Semua ditolak dengan `Chip is invalid` / `Chip mismatch` /
  `Cartridge authentication error`** → fokus ke jenis kartu magic, UID, atau
  signature; mengubah counter tidak akan membantu.
- **`Ink Box Check-01..05`** → printer membaca kartu tetapi pemeriksaan
  isi/counter gagal; coba counter lain dan varian fill.

Catat hasil per file (misalnya di `CATATAN_UJI.md`) agar urutan pengujian tidak
berulang.

---

## 7. Peringatan

- Menulis kartu akan menimpa seluruh isi, termasuk blok 0/UID.
- Hanya gunakan pada kartu dan printer milik sendiri.
- Cadangkan dump asli sebelum menulis; GTInk melakukannya otomatis kecuali
  `--no-backup`.
- Menulis blok 0 dengan data yang salah dapat membuat kartu tidak terbaca.
- Kartu magic Gen1a/Gen2/Gen4 dapat terdeteksi sebagai kartu palsu oleh
  printer. Clone yang benar secara data belum tentu diterima.
- Jangan menulis ke kartu asli pabrik; gunakan kartu magic yang bisa
  dipulihkan.

---

## 8. Struktur teknis

### Blok dan record

```text
Blok 0        : UID, BCC, SAK, ATQA, manufacturer
Blok 1-2      : data bebas (nol)
Blok 3        : trailer sektor 0
Blok 4-32     : record 1 (29 blok fisik; trailer 7,11,15,19,23,27,31)
Blok 33-61    : record 2 (29 blok fisik; trailer 35,39,43,47,51,55,59)
Blok 62-63    : data/trailer sektor 15
```

Record data (tanpa trailer):

```text
Payload : blok 4,5,6,8,9,10,12,13,14,16,17,18       (12 blok, 192 byte)
Tail    : blok 20,21,22,24,25,26,28,29,30,32         (10 blok, 160 byte)
```

Counter:

```text
Blok 29, offset 10..11 : 16-bit little-endian
Blok 58, offset 10..11 : salinan
Contoh 65000 = 0xFDE8 -> byte E8 FD
```

### Fill tail

- Blok 20/49: dua byte pertama `FE FE`, sisanya fill.
- Blok 21/22/24/25/26/28 dan 50/52/53/54/56/57: fill penuh.
- Blok 29/58: 10 byte header fill, lalu counter 2 byte, lalu 4 byte nol.
- Blok 30/32 dan 60/62: selalu nol.

### Nominal counter

- 65000 (`0xFDE8`) dipilih karena paling dekat dengan nilai chip penuh
  (64016-64606) dan merupakan angka bulat yang masuk akal sebagai kapasitas
  nominal.
- 65535 (`0xFFFF`) adalah batas maksimum field 16-bit.
- Nilai asli dari dump lain (64606, 64516, 64016) juga tersedia sebagai kontrol.

---

## 9. Troubleshooting

### Client Proxmark3 keluar tanpa pesan

Tambahkan folder DLL ke `PATH`:

```powershell
$env:PATH = "C:\ProxSpace\msys2\mingw64\bin;" + $env:PATH
```

GTInk melakukan ini otomatis, tetapi cara manual berguna saat menjalankan
client langsung.

### Port salah atau `invalid serial port`

```powershell
py gtink.py ports
```

Cari entri dengan `VID_9AC4` atau nama `ICEMAN`. Di mesin ini portnya `COM11`.

Pesan `invalid serial port` juga muncul bila port sedang dipakai aplikasi lain
(client Proxmark3 lain, SharkCode, atau terminal lain). Tutup aplikasi tersebut
lalu coba lagi. Cek proses yang memakai client:

```powershell
Get-CimInstance Win32_Process -Filter "Name='proxmark3.exe'" | Select-Object ProcessId,CommandLine
```

### `hf mf dump` gagal / key salah

Letakkan file key 192 byte di folder kerja dengan nama
`hf-mf-<UID>-key.bin`, atau berikan `--keys`. Key default semua `FF`.

### Kartu tidak terdeteksi

- Pastikan kartu tepat di atas antena.
- Coba `hf search` manual.
- Untuk Gen1a, coba `hf mf cgetblk --blk 0` atau `hf 14a info`.

### Verifikasi menemukan blok berbeda

- Pastikan kartu masih di antena.
- Baca ulang dengan `py gtink.py read --out cek.bin`.
- Untuk Gen2, blok 0/UID mungkin tidak bisa ditulis; cek kemampuan kartu.
- Untuk Gen4, pastikan kartu sudah dikonfigurasi sebagai MIFARE Classic 1K.

### Printer tetap menolak

- Coba exact clone untuk memisahkan masalah counter dari masalah kartu magic.
- Coba UID baru.
- Coba sumber payload lain.
- Jika semua ditolak, kemungkinan printer memakai signature/UID binding atau
  mendeteksi kartu magic; data counter saja tidak cukup.

---

## 10. Peta file

```text
gtink.py                  entry point CLI
gtink_gui.py              entry point GUI
gtink.cmd                 pembungkus CLI
gtink_gui.cmd             pembungkus GUI
gtink/
  card.py                 parser, layout record, edit counter/UID/fill, validasi
  analysis.py             tabel, analisis, kandidat counter, laporan
  clone.py                spesifikasi clone, paket rekomendasi, manifest
  proxmark.py             deteksi client/port, baca/tulis/verifikasi, script
  replay.py               state ISO14443-4 + perintah hf 14a simaid
  cli.py                  perintah CLI
  gui.py                  antarmuka Tkinter
  selftest.py             uji offline 12 pemeriksaan
  paths.py                resolusi path proyek
tests/                    unit test (unittest)
clones/                   11 clone + manifest + README_UJI + scripts/
backups/                  backup kartu sebelum ditulis (dibuat saat dipakai)
tij gt1000 CHIP INK/      empat dump sumber
printer_test.py           jalankan emulator set A/B/C/factory
proxmark_patch/           eajet_sim.c, splice_sim.py, build_flash.py
docs/                     manual FMCOS dan hasil ekstraksi
logs/                     log uji printer, sniff, dan flash
```

---

## 11. Uji offline

```powershell
py gtink.py selftest
py -m unittest discover -s tests -v
```

Selftest memeriksa:

- keempat dump dan counter yang dikenal;
- BCC, payload, tail, dan validasi;
- exact clone identik;
- edit counter hanya mengubah 4 byte;
- ganti UID menghitung ulang BCC;
- normalisasi fill low-ink;
- round-trip JSON/EML;
- paket rekomendasi + manifest + script;
- sintaks script Gen1a/Gen2/Gen4;
- laporan analisis.
