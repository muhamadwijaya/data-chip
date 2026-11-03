#!/usr/bin/env bash
set +e
IMG='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
echo "=== lost+found listing (first 100) ==="
debugfs -R 'ls -l /lost+found' "$IMG" 2>&1 | head -100
echo "=== count ==="
debugfs -R 'ls -l /lost+found' "$IMG" 2>&1 | wc -l
echo "=== stat lost+found ==="
debugfs -R 'stat /lost+found' "$IMG" 2>&1 | head -40
echo DONE
