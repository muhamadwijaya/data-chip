#!/usr/bin/env bash
set +e
echo "=== top-level entries in lost+found (non-dir first) ==="
find /mnt/rfs/lost+found -maxdepth 1 ! -type d -printf '%y %10s %p\n' 2>/dev/null | head -40
echo "top files: $(find /mnt/rfs/lost+found -maxdepth 1 -type f 2>/dev/null | wc -l)"
echo "total files: $(find /mnt/rfs/lost+found -type f 2>/dev/null | wc -l)"
echo "total dirs:  $(find /mnt/rfs/lost+found -type d 2>/dev/null | wc -l)"
echo
echo "=== sample dirs ==="
for d in '/mnt/rfs/lost+found/#13' '/mnt/rfs/lost+found/#1080' '/mnt/rfs/lost+found/#1623'; do
  echo "--- $d ---"
  ls -la "$d" 2>&1 | head -25
done
echo
echo "=== find likely targets by name ==="
find /mnt/rfs/lost+found \( -iname '*EAN*' -o -iname '*.mky' -o -iname '*cartridge*' -o -iname 'libsdk*' -o -iname 'LOOGAL*' \) 2>/dev/null | head -50
echo DONE
