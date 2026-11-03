#!/usr/bin/env bash
set +e
for f in '/mnt/rfs/lost+found/#100' '/mnt/rfs/lost+found/#1000' '/mnt/rfs/lost+found/#5000' '/mnt/rfs/lost+found/#7000'; do
  echo "=== $f ==="
  ls -l "$f" 2>/dev/null
  head -c 128 "$f" 2>/dev/null | xxd | head -4
  echo "unique bytes in first 64K:"; head -c 65536 "$f" 2>/dev/null | od -An -tu1 -v | tr ' ' '\n' | sort -u | wc -l
done
