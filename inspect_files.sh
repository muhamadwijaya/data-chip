#!/usr/bin/env bash
set +e
for f in '/mnt/rfs/lost+found/#11' '/mnt/rfs/lost+found/#29' '/mnt/rfs/lost+found/#30' '/mnt/rfs/lost+found/#1715' '/mnt/rfs/lost+found/#13'; do
  echo "=== $f ==="
  ls -l "$f" 2>/dev/null
  head -c 256 "$f" 2>/dev/null | xxd | head -8
done
