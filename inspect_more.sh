#!/usr/bin/env bash
set +e
IMG='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
mountpoint -q /mnt/rfs || mount -o ro,loop "$IMG" /mnt/rfs
echo "=== file samples ==="
for f in '/mnt/rfs/lost+found/#100' '/mnt/rfs/lost+found/#1000' '/mnt/rfs/lost+found/#5000' '/mnt/rfs/lost+found/#7000'; do
  echo "=== $f ==="
  ls -l "$f" 2>/dev/null
  head -c 128 "$f" 2>/dev/null | xxd | head -4
  printf 'unique bytes first 64K: '; head -c 65536 "$f" 2>/dev/null | od -An -tu1 -v | tr ' ' '\n' | grep -v '^$' | sort -u | wc -l
done
umount /mnt/rfs 2>/dev/null
echo "=== raw samples ==="
python3 - <<'PY'
f='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
import os
with open(f,'rb') as fh:
    for off in [0x60000000,0xB0000000,0x100000000,0x150000000,0x1B0000000]:
        fh.seek(off); b=fh.read(256)
        print('offset',hex(off),'unique',len(set(b)),'head',b[:64].hex())
PY
echo DONE
