#!/usr/bin/env bash
set +e
cd '/mnt/o/tij gt 1000/keycrack'
echo "=== fdisk sdcard_rootfs.img ==="
fdisk -l sdcard_rootfs.img 2>&1 | head -30
echo "=== fdisk sdcard_full2g.img ==="
fdisk -l sdcard_full2g.img 2>&1 | head -30
echo "=== except bytes at partition start (1MB) ==="
xxd -s 1048576 -l 256 sdcard_rootfs.img
echo "=== fat dir listing (mtools) ==="
which mdir mtype 2>/dev/null
mdir -i sdcard_rootfs.img@@1048576 :: 2>&1 | head -40
echo "=== ext4 superblock scan in sdcard_rootfs.img ==="
python3 - <<'PY'
f='sdcard_rootfs.img'
import os
sz=os.path.getsize(f)
with open(f,'rb') as fh:
    for off in range(0,sz,1024*1024):
        fh.seek(off+0x438)
        if fh.read(2)==b'\x53\xef':
            fh.seek(off)
            head=fh.read(16)
            # plausible superblock: inodes_count sane, block_size
            fh.seek(off+0x18); log_bs=int.from_bytes(fh.read(4),'little')
            print('superblock?',hex(off),'head',head.hex(),'log_bs',log_bs)
PY
echo DONE
