#!/usr/bin/env bash
set +e
cd '/mnt/o/tij gt 1000/balea'
echo "=== file types + md5 first 4KB ==="
for f in e00.bin e01.bin e02.bin e03.bin e04.bin e05.bin e06.bin e07.bin e064.bin e128.bin e192.bin e256.bin emmc_0_64M.bin; do
  printf '%-15s %12s  ' "$f" "$(stat -c%s "$f")"
  file -b "$f" | cut -c1-90
  md5sum "$f" | awk '{print "   md5="$1}'
done
echo
echo "=== first 64 bytes each ==="
for f in e00.bin e01.bin e02.bin e03.bin e04.bin e05.bin e06.bin e07.bin e064.bin e128.bin e192.bin e256.bin; do
  printf '%-15s ' "$f"; head -c 32 "$f" | xxd -p
done
echo
echo "=== ext4 magic at 0x438 and 1MB ==="
python3 - <<'PY'
import os
for f in ['e00.bin','e01.bin','e02.bin','e03.bin','e04.bin','e05.bin','e06.bin','e07.bin','e064.bin','e128.bin','e192.bin','e256.bin']:
    d=open(f,'rb').read(2*1024*1024)
    hits=[hex(o) for o in (0x438,0x10438) if d[o:o+2]==b'\x53\xef']
    print(f, 'ext4magic',hits, 'size',os.path.getsize(f))
PY
echo DONE
