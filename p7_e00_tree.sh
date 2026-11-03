#!/usr/bin/env bash
set +e
B='/mnt/o/tij gt 1000/balea/New folder'
OUT='/var/tmp/p7_e00.img'
dd if="$B/e00.bin" of="$OUT" bs=1M skip=70 status=none
ls -l "$OUT"
echo "=== superblock ==="
dumpe2fs -h "$OUT" 2>/dev/null | egrep 'volume|Block count|Free blocks|Inode count|Block size|state|Last mount|Last write|Mount count|Inode size'
echo "=== e2fsck -fn ==="
e2fsck -fn "$OUT" 2>&1 | tail -20
echo "=== / ==="
debugfs -R 'ls -l /' "$OUT" 2>/dev/null | head -80
for d in /LOOGAL /etc /usr /usr/bin /usr/lib /lib /bin /sbin /root /opt /app /data /mnt /home /tmp /var /dev; do
  echo "=== $d ==="
  debugfs -R "ls -l $d" "$OUT" 2>/dev/null | head -60
done
echo DONE
