#!/usr/bin/env bash
set +e
cd '/mnt/o/tij gt 1000/keycrack'
for f in sdcard_rootfs.img sdcard_rootfs.img.gz sdcard_ean.img.gz sdcard_full2g.img sdcard_feta.img sdcard_stage1.img sdcard_dump2a.img sdcard_dump2b.img sdcard_dump2c.img; do
  [ -e "$f" ] || continue
  echo "=== $f ==="
  ls -l "$f"
  file "$f"
  case "$f" in
    *.gz) gzip -l "$f" 2>&1 | head -4 ;;
    *) head -c 64 "$f" | xxd | head -4 ;;
  esac
done
echo "=== rootfs_full vs others first 512 ==="
xxd -l 128 rootfs/rootfs_full.img
echo "=== mount status / free ==="
df -h /var/tmp | tail -1
