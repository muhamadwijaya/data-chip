#!/usr/bin/env bash
set +e
IMG='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
echo "=== dumpe2fs ==="
dumpe2fs -h "$IMG" 2>/dev/null | egrep 'Filesystem volume name|Block count|Block size|Free blocks|Free inodes|Filesystem state|Last checked|Last mount|Filesystem features|Inode count'
echo "=== e2fsck -fn ==="
e2fsck -fn "$IMG" 2>&1 | tail -40
echo "=== / ==="
debugfs -R 'ls -l /' "$IMG" 2>/dev/null
echo "=== /LOOGAL ==="
debugfs -R 'ls -l /LOOGAL' "$IMG" 2>/dev/null | head -100
echo "=== /LOOGAL/libs ==="
debugfs -R 'ls -l /LOOGAL/libs' "$IMG" 2>/dev/null | head -100
echo "DONE"
