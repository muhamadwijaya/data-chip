#!/usr/bin/env bash
set +e
IMG='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
for off in 0x044000000 0x044001000 0x04c000000 0x054000000 0x05c000000 0x064000000; do
  echo "=== offset $off ==="
  dd if="$IMG" bs=1 skip=$((off)) count=256 status=none | xxd | head -8
  echo "unique in 64K: $(dd if="$IMG" bs=1 skip=$((off)) count=65536 status=none | od -An -tu1 -v | tr ' ' '\n' | grep -v '^$' | sort -u | wc -l)"
  echo "strings:"; dd if="$IMG" bs=1 skip=$((off)) count=65536 status=none | strings -n 6 | head -10
done
echo "=== ELF magic scan whole image ==="
python3 - <<'PY'
f='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
import os
hits=[]; pos=0
with open(f,'rb',buffering=0) as fh:
    while True:
        b=fh.read(16*1024*1024)
        if not b: break
        i=0
        while True:
            j=b.find(b'\x7fELF',i)
            if j<0: break
            hits.append(pos+j); i=j+1
        pos+=len(b)
print('ELF hits',len(hits),[hex(x) for x in hits[:50]])
# map to 64MB segment good/bad quickly
PY
echo DONE
