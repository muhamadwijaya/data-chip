PAKET UJI CLONE CHIP EAJet / GT1000
================================================

Urutan pengujian yang disarankan:
1. Tulis file exact (kontrol) lebih dulu, lalu pasang ke printer.
2. Catat pesan printer. Jika exact diterima, lanjut ke counter 65000.
3. Jika 65000 ditolak, coba max_65535.
4. Jika printer menolak UID sumber, coba file newuid (UID baru).
5. Coba juga sumber lain (5EEFAB9B / FE7EA17E) dengan counter 65000.
6. Untuk chip low-ink, coba keep00 lalu fillFF.

Daftar file:
- 1EB75C2C_exact_64016.bin: UID 1EB75C2C, counter 64016 (0xFA10), fill=asli
  Kontrol: clone persis dari dump sumber. Uji dulu apakah printer menerima kartu magic/UID hasil clone.
- 1EB75C2C_full_65000.bin: UID 1EB75C2C, counter 65000 (0xFDE8), fill=asli
  Kandidat utama: counter nominal penuh 65000, fill dan payload dipertahankan dari chip penuh.
- 1EB75C2C_max_65535.bin: UID 1EB75C2C, counter 65535 (0xFFFF), fill=asli
  Kandidat cadangan: counter maksimum 16-bit 65535.
- 1EB75C2C_full_65000_newuid_92A7CC05.bin: UID 92A7CC05, counter 65000 (0xFDE8), fill=asli
  UID baru yang diturunkan dari payload, counter 65000. Untuk menguji apakah printer menolak UID yang sudah dikenal atau mendeteksi rollback counter.
- 5EEFAB9B_exact_64606.bin: UID 5EEFAB9B, counter 64606 (0xFC5E), fill=asli
  Kontrol sumber 5EEFAB9B: clone persis, payload dan counter asli dipertahankan.
- 5EEFAB9B_full_65000.bin: UID 5EEFAB9B, counter 65000 (0xFDE8), fill=asli
  Kandidat sumber 5EEFAB9B: counter 65000, payload sumber dipertahankan.
- FE7EA17E_exact_64516.bin: UID FE7EA17E, counter 64516 (0xFC04), fill=asli
  Kontrol sumber FE7EA17E: clone persis, payload dan counter asli dipertahankan.
- FE7EA17E_full_65000.bin: UID FE7EA17E, counter 65000 (0xFDE8), fill=asli
  Kandidat sumber FE7EA17E: counter 65000, payload sumber dipertahankan.
- BE8AAA9B_exact_12107.bin: UID BE8AAA9B, counter 12107 (0x2F4B), fill=asli
  Kontrol chip low-ink: counter dan fill 00 dipertahankan.
- BE8AAA9B_full_65000_keep00.bin: UID BE8AAA9B, counter 65000 (0xFDE8), fill=asli
  Chip low-ink dinaikkan ke 65000 dengan fill 00 asli. Payload low-ink dipertahankan.
- BE8AAA9B_full_65000_fillFF.bin: UID BE8AAA9B, counter 65000 (0xFDE8), fill=FF
  Chip low-ink dinaikkan ke 65000 dan tail dinormalisasi ke format chip penuh (FF).

Perintah tulis Gen1a (magic card):
  py gtink.py write --file <file.bin> --backend gen1a --port COM11 --yes

Script Proxmark3 ada di folder scripts/.
Peringatan: hanya gunakan pada kartu/printer milik sendiri. Menulis blok 0 dapat mengubah UID dan membuat kartu tidak terbaca jika data blok 0 salah. Cadangkan dump asli sebelum menulis.

Jika printer menolak semua file dengan 'Chip invalid' atau 'Chip mismatch', counter bukan penyebabnya; kemungkinan ada signature/UID binding atau kartu magic terdeteksi.
