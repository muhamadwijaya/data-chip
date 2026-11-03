#!/usr/bin/env bash
set +e
B='/mnt/o/tij gt 1000/balea/New folder'
for f in e00.bin e01.bin e02.bin e03.bin; do
  echo "=== $f ==="
  for off in 0x1000 0x100000 0x1000000 0x4000000 0x8000000 0xC000000 0xF000000; do
    printf '  off %-10s word: ' "$off"
    dd if="$B/$f" bs=1 skip=$((off)) count=16 status=none | xxd -p
  done
done
echo "=== check linear counter in e01 around 1MB ==="
python3 - <<'PY'
import struct
for name in ['e00.bin','e01.bin','e02.bin']:
    p='/mnt/o/tij gt 1000/balea/New folder/'+name
    d=open(p,'rb').read(2*1024*1024)
    print(name, 'first nonzero offset', next((i for i,b in enumerate(d) if b), None))
    for off in [0x1000,0x2000,0x100000,0x200000]:
        v=struct.unpack_from('<I',d,off)[0]
        print('  ',hex(off),hex(v))
PY
echo "=== FAT dir of sdcard_full2g / sdcard_rootfs ==="
cd '/mnt/o/tij gt 1000/keycrack'
mdir -i sdcard_full2g.img@@1048576 :: 2>&1 | head -30
mdir -i sdcard_rootfs.img@@1048576 :: 2>&1 | head -30
echo DONE
