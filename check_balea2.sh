#!/usr/bin/env bash
set +e
B='/mnt/o/tij gt 1000/balea'
echo "=== New folder e00-e07 ==="
for f in "$B/New folder"/e0*.bin; do
  printf '%-15s %12s  ' "$(basename "$f")" "$(stat -c%s "$f")"
  file -b "$f" | cut -c1-90
  printf '%-15s md5=' "$(basename "$f")"; md5sum "$f" | awk '{print $1}'
  printf '%-15s head=' "$(basename "$f")"; head -c 32 "$f" | xxd -p
done
echo
echo "=== root 64MB chunks ==="
for f in "$B"/e064.bin "$B"/e128.bin "$B"/e192.bin "$B"/e256.bin "$B"/emmc_0_64M.bin; do
  printf '%-15s %12s  ' "$(basename "$f")" "$(stat -c%s "$f")"
  file -b "$f" | cut -c1-90
  printf '%-15s head=' "$(basename "$f")"; head -c 32 "$f" | xxd -p
done
echo
echo "=== eMMC ext4 magic search (offsets in each 256MB chunk) ==="
python3 - <<'PY'
import os,glob
for f in sorted(glob.glob('/mnt/o/tij gt 1000/balea/New folder/e0*.bin')):
    sz=os.path.getsize(f); hits=[]
    with open(f,'rb') as fh:
        for off in range(0,min(sz,300*1024*1024),1024*1024):
            fh.seek(off+0x438); b=fh.read(2)
            if b==b'\x53\xef': hits.append(hex(off))
    print(os.path.basename(f), 'size',sz,'ext4 superblock at',hits[:10])
PY
echo DONE
