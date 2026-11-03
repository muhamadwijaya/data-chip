#!/usr/bin/env bash
set +e
B='/mnt/o/tij gt 1000/balea/New folder'
OUT='/var/tmp/p7_sparse2.img'
rm -f "$OUT"
truncate -s 7516192768 "$OUT"
dd if="$B/e00.bin" of="$OUT" bs=1M skip=70 conv=notrunc status=none
ls -l "$OUT"; du -h "$OUT"
echo "=== / ==="
debugfs -R 'ls -l /' "$OUT" 2>&1 | head -100
for d in /LOOGAL /etc /usr /usr/bin /usr/lib /lib /bin /sbin /root /opt /app /data /mnt /home /tmp /var /dev; do
  echo "=== $d ==="
  debugfs -R "ls -l $d" "$OUT" 2>&1 | head -50
done
echo DONE
