PAKET DIAGNOSTIK TAMBAHAN
==========================

File-file ini dibuat untuk mengisolasi penyebab penolakan printer.

- 1EB75C2C_counter_64017.bin:
  Clone persis, hanya counter diubah dari 64016 ke 64017.
  Jika ditolak: printer mendeteksi perubahan counter (rollback/checksum).
  Jika diterima: printer menerima counter yang sedikit berubah.

- 1EB75C2C_payload_changed.bin:
  Clone persis, hanya 1 byte pertama payload diubah (0x7A -> 0x7B).
  Jika ditolak: printer memeriksa integritas payload.
  Jika diterima: payload tidak diperiksa.

- 1EB75C2C_tail_fill_00.bin:
  Clone persis, counter 64016, tetapi tail fill diubah dari FF ke 00.
  Jika ditolak: fill harus sesuai dengan status tinta/counter.
  Jika diterima: fill tidak diperiksa.

- 1EB75C2C_full_65000_newuid_1EB75C2D.bin:
  Counter 65000, UID baru 1EB75C2D (prefix manufaktur 1E dipertahankan).
  Jika ditolak: printer menolak UID yang tidak dikenal atau mendeteksi rollback.
  Jika diterima: UID baru diterima, masalahnya hanya UID asli.

Urutan uji disarankan setelah uji utama:
1. exact (64016)
2. counter_64017
3. payload_changed
4. tail_fill_00
5. full_65000
6. max_65535
7. newuid_1EB75C2D
8. newuid_92A7CC05

Catat setiap hasil di CATATAN_UJI.md.