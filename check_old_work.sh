#!/usr/bin/env bash
set +e
echo "=== emmc_0_256.bin vs e00 ==="
md5sum /var/tmp/emmc_0_256.bin '/mnt/o/tij gt 1000/balea/New folder/e00.bin'
cmp -l /var/tmp/emmc_0_256.bin '/mnt/o/tij gt 1000/balea/New folder/e00.bin' 2>/dev/null | head -5
echo "first diff count: $(cmp -l /var/tmp/emmc_0_256.bin '/mnt/o/tij gt 1000/balea/New folder/e00.bin' 2>/dev/null | wc -l)"
echo
echo "=== p7_sparse root ==="
debugfs -R 'ls -l /' /var/tmp/p7_sparse.img 2>&1 | head -60
echo "=== p7root tree ==="
find /var/tmp/p7root -maxdepth 2 -printf '%y %10s %p\n' 2>/dev/null | head -100
echo
echo "=== loogal EAN dump ==="
ls -l /var/tmp/loogal 2>/dev/null
file /var/tmp/loogal/* 2>/dev/null
xxd -l 64 /var/tmp/loogal/EAN 2>/dev/null
echo
echo "=== EAN_7gb.bin ==="
ls -l /var/tmp/EAN_7gb.bin
xxd -l 64 /var/tmp/EAN_7gb.bin
python3 - <<'PY'
d=open('/var/tmp/EAN_7gb.bin','rb').read()
print('size',len(d),'FF%',round(d.count(255)*100/len(d),1),'00%',round(d.count(0)*100/len(d),1),'unique',len(set(d)))
print('ELF',d[:4]==b'\x7fELF')
PY
echo DONE
