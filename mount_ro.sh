#!/usr/bin/env bash
set +e
IMG='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
echo "whoami: $(whoami)"
mkdir -p /mnt/rfs
mountpoint -q /mnt/rfs && umount /mnt/rfs
sudo mount -o ro,loop "$IMG" /mnt/rfs 2>&1 && echo MOUNT_OK || echo MOUNT_FAIL
echo "=== /mnt/rfs ==="
ls -la /mnt/rfs 2>&1 | head
echo "=== sample subdirs ==="
for d in '/mnt/rfs/lost+found/#13' '/mnt/rfs/lost+found/#1080' '/mnt/rfs/lost+found/#1623'; do
  echo "--- $d ---"
  ls -la "$d" 2>&1 | head -20
done
echo "=== regular files at top of lost+found ==="
find /mnt/rfs/lost+found -maxdepth 1 -type f 2>/dev/null | head -20
echo "count top files: $(find /mnt/rfs/lost+found -maxdepth 1 -type f 2>/dev/null | wc -l)"
echo "count all files: $(find /mnt/rfs/lost+found -type f 2>/dev/null | wc -l)"
echo DONE
