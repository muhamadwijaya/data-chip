# Catatan Uji Printer

Isi tabel ini setiap kali mencoba satu file clone di printer. Tulis pesan
printer persis seperti yang muncul di layar.

| Tanggal | File | UID | Counter | Pesan printer | Diterima? |
|---|---|---|---|---:|---|
| 2026-10-26 | `1EB75C2C_exact_64016.bin` | `1EB75C2C` | 64016 | Volume penuh, lalu `ERROR:NO1.INKBOX_CHECK_ERR_03` | Tidak |
|  | `1EB75C2C_full_65000.bin` | `1EB75C2C` | 65000 |  |  |
|  | `1EB75C2C_max_65535.bin` | `1EB75C2C` | 65535 |  |  |
|  | `1EB75C2C_full_65000_newuid_92A7CC05.bin` | `92A7CC05` | 65000 |  |  |
|  | `5EEFAB9B_exact_64606.bin` | `5EEFAB9B` | 64606 |  |  |
|  | `5EEFAB9B_full_65000.bin` | `5EEFAB9B` | 65000 |  |  |
|  | `FE7EA17E_exact_64516.bin` | `FE7EA17E` | 64516 |  |  |
|  | `FE7EA17E_full_65000.bin` | `FE7EA17E` | 65000 |  |  |
|  | `BE8AAA9B_exact_12107.bin` | `BE8AAA9B` | 12107 |  |  |
|  | `BE8AAA9B_full_65000_keep00.bin` | `BE8AAA9B` | 65000 |  |  |
|  | `BE8AAA9B_full_65000_fillFF.bin` | `BE8AAA9B` | 65000 |  |  |
|  | `1EB75C2C_counter_64017.bin` | `1EB75C2C` | 64017 |  |  |
|  | `1EB75C2C_payload_changed.bin` | `1EB75C2C` | 64016 |  |  |
|  | `1EB75C2C_tail_fill_00.bin` | `1EB75C2C` | 64016 |  |  |
|  | `1EB75C2C_full_65000_newuid_1EB75C2D.bin` | `1EB75C2D` | 65000 |  |  |

## Cara mengisi

1. Tulis satu file ke kartu magic dengan GTInk.
2. Pasang kartrid ke printer, nyalakan, dan tunggu pesan.
3. Catat pesan persis (misalnya `Chip is invalid`, `Chip mismatch`,
   `Ink Box Check-01`, atau status sisa tinta).
4. Jika printer menerima, catat apakah tinta terbaca penuh.
5. Jangan menulis file berikutnya sebelum mencatat hasil sebelumnya.

## Interpretasi cepat

- Exact ditolak juga: masalah kartu magic/UID/signature, bukan counter.
- Exact diterima, 65000 ditolak: batas nominal/rollback counter.
- 65000 diterima tetapi tinta tidak penuh: counter mungkin bukan satu-satunya
  penentu; periksa payload/format tail.
- Semua ditolak: kemungkinan printer memakai autentikasi kartu asli.

### Catatan hasil Gen1a 2026-10-26

Kartu `1EB75C2C_exact_64016.bin` (Gen1a, UID `1EB75C2C`, counter 64016)
sempat terbaca **volume tinta penuh**, tetapi beberapa saat kemudian printer
menampilkan `ERROR:NO1.INKBOX_CHECK_ERR_03`. Artinya pembacaan MIFARE/payload
sudah masuk dan level tinta dikenali, tetapi pemeriksaan berikutnya gagal.
Kemungkinan pemeriksaan itu adalah konsistensi data ISO-DEP/secure messaging,
UID/ink box, atau counter. Uji emulator di bawah perlu melihat APDU mana yang
dikirim printer setelah pembacaan MIFARE.

## Uji emulator ISO14443-4 (Proxmark3)

Kartu asli memakai ISO14443-4/APDU, bukan MIFARE Classic. Karena itu clone
Gen1a selalu ditolak. Firmware Proxmark3 sudah dipatch dengan handler APDU
khusus EAJet (`proxmark_patch/eajet_sim.c`).

State yang tersedia di `printer_test.py`:

| Set | File 0004 | File 0003 | Secure read 0006/0007 | Keterangan |
|---|---|---|---|---|
| A | `A0 A6` | `20260317`, `DB 05` | `...A0 18`, MAC `37E1DD06` / `54E832B6` | awal trace |
| B | `28 A6` | `20260516`, `D8 05` | `...DF 18`, MAC `A387B6A5` / `78B0373B` | setelah cetak 1 |
| C | `A1 A6` | `20260516`, `D8 05` | `...20 18`, MAC `5E327B97` / `7A4854FF` | setelah cetak 2 |
| factory | hasil ROR2 dump MIFARE `FE7EA17E` | `20260516` | set C | cadangan pabrik |

Perintah uji:

```powershell
# firmware dan state harus memakai set yang sama
py proxmark_patch\build_flash.py --set C --flash
py printer_test.py --set C --seconds 120

py proxmark_patch\build_flash.py --set A --flash
py printer_test.py --set A --seconds 120

py proxmark_patch\build_flash.py --set FACTORY --flash
py printer_test.py --set factory --seconds 120

py printer_test.py --set C --seconds 120 --debug
```

`--debug` menampilkan APDU yang diterima firmware. Log tersimpan di `logs/`.
Setelah flash, COM11 biasanya hilang sebentar; cabut/colok ulang USB bila perlu.

Hasil yang perlu dicatat:

| Tanggal | Set | Pesan printer | Diterima? | Catatan |
|---|---|---|---|---|
| 2026-10-26 | C (replay) | Cek berhasil / printer siap | Ya | Secure read file 0006 command MAC `324E0F43`, file 0007 `18540805`; response MAC `5E327B97`/`7A4854FF` diterima. Printer melanjutkan penulisan 0004/0005 dan 0006, lalu siap. |
|  | B |  |  |  |
|  | A |  |  |  |
|  | factory |  |  |  |

Set C sudah diterima. Set A/B/factory tinggal diuji dengan firmware yang sesuai;
challenge dan response MAC-nya sudah disiapkan. Jika sebuah set berhenti tepat
setelah `SECURE READ`, pastikan firmware di-build untuk set yang sama
(`build_flash.py --set ...`) dan lihat log `--debug`.

## Uji replay set C (2026-10-26) - BERHASIL

Firmware Proxmark3 dipatch dengan `eajet_sim.c` yang mengembalikan GET CHALLENGE
`B9 BE 71 5F` setelah `SELECT 0006` dan `A6 1D 5A 69` setelah `SELECT 0007`.
Printer mengirim command MAC `32 4E 0F 43` (file 0006) dan `18 54 08 05`
(file 0007), persis sesuai `trace_full_new.txt`. Emulator mengembalikan response
MAC `5E 32 7B 97` dan `7A 48 54 FF`. Printer menerima dan menampilkan
`Cek berhasil / printer siap`.

Kesimpulan: autentikasi kartu (EXTERNAL AUTH) tetap diterima, dan secure read
diverifikasi dengan MAC. Replay challenge yang sesuai dengan response MAC
mengalahkan pemeriksaan MAC tanpa perlu mengetahui kunci DES.

Generalisasi untuk set A/B/factory:
- A: challenge 0006 = `69 1D 4F C3`, 0007 = `1A 6A CE 1F`
- B: challenge 0006 = `96 BF 9A 55`, 0007 = `87 7E 50 87`
- C/factory: challenge 0006 = `B9 BE 71 5F`, 0007 = `A6 1D 5A 69`

Gunakan `proxmark_patch/splice_sim.py --set A/B/C/FACTORY` lalu build & flash.
Helper: `proxmark_patch/build_flash.py --set A --flash`."
