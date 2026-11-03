#!/usr/bin/env bash
set +e
IMG='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
echo "=== stat inode 110 ==="
debugfs -R 'stat <110>' "$IMG" 2>&1 | head -60
echo "=== dump inode 110 ==="
rm -f /var/tmp/inode110.bin
debugfs -R 'dump <110> /var/tmp/inode110.bin' "$IMG" 2>&1
ls -l /var/tmp/inode110.bin
file /var/tmp/inode110.bin
head -c 128 /var/tmp/inode110.bin | xxd
python3 - <<'PY'
d=open('/var/tmp/inode110.bin','rb').read()
print('size',len(d),'FF%',round(d.count(255)*100/len(d),1),'00%',round(d.count(0)*100/len(d),1),'unique',len(set(d)))
for s in [b'cleanCartridge',b'Cartridge',b'.mky',b'System.mky',b'/dev/i2c',b'DES',b'ExtAuth',b'FM1208',b'ELF']:
    print(' ',s.decode(errors='replace'),'->',d.count(s),'first',d.find(s))
PY
echo "=== extents and 64MB segment goodness ==="
python3 - <<'PY'
import subprocess,re
img='/mnt/o/tij gt 1000/keycrack/rootfs/rootfs_full.img'
out=subprocess.run(['debugfs','-R','stat <110>',img],capture_output=True,text=True).stdout
print(out)
# parse extents "BLOCKS:" lines like (0-9):12345 or (IND):...
for line in out.splitlines():
    if re.match(r'\s*\(',line):
        print('EXT',line.strip())
PY
echo DONE
