#!/usr/bin/env bash
set +e
B='/mnt/o/tij gt 1000/balea'
echo "=== sizes/md5 ==="
for f in "$B/emmc1_2m.bin" "$B/emmc2_2m.bin" "$B/emmc_0_64M.bin"; do
  printf '%-25s %10s ' "$(basename "$f")" "$(stat -c%s "$f")"; md5sum "$f" | awk '{print $1}'
  file -b "$f" | cut -c1-100
done
echo "=== compare to e00 first 2MB / 64MB ==="
python3 - <<'PY'
import hashlib,os
B='/mnt/o/tij gt 1000/balea'
def h(fn,n):
    d=open(fn,'rb').read(n)
    return hashlib.md5(d).hexdigest(), d[:64].hex()
e00=os.path.join(B,'New folder','e00.bin')
for fn,n in [(os.path.join(B,'emmc1_2m.bin'),2*1024*1024),(os.path.join(B,'emmc2_2m.bin'),2*1024*1024),(os.path.join(B,'emmc_0_64M.bin'),64*1024*1024)]:
    a=h(fn,n); b=h(e00,n)
    print(os.path.basename(fn),'md5',a[0][:12],'e00',b[0][:12],'MATCH',a[0]==b[0])
    print('  head',a[1])
    print('  e00 ',b[1])
print('emmc1 vs emmc2 first 2M',h(os.path.join(B,'emmc1_2m.bin'),2*1024*1024)[0]==h(os.path.join(B,'emmc2_2m.bin'),2*1024*1024)[0])
PY
echo "=== emmc2_2m first 512 bytes ==="
xxd -l 512 "$B/emmc2_2m.bin"
echo "=== strings emmc2 ==="
strings -n 6 "$B/emmc2_2m.bin" | head -30
echo DONE
