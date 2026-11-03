#!/usr/bin/env bash
set +e
IMG='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
mkdir -p /mnt/rfs
mountpoint -q /mnt/rfs && umount /mnt/rfs
timeout 60 mount -o ro,loop "$IMG" /mnt/rfs 2>&1
echo "mount_exit=$?"
mount | grep rfs
ls -la /mnt/rfs 2>&1 | head
