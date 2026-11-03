#!/usr/bin/env bash
set +e
P=/var/tmp/p7_sparse.img
for d in /LOOGAL /LOOGAL/libs /LOOGAL/build /LOOGAL/data /LOOGAL/PRINTFILE /etc /usr /usr/lib /usr/bin /lib /bin /sbin /root /opt /opt/* /home /var /media /wave /mnt; do
  echo "=== $d ==="
  debugfs -R "ls -l $d" "$P" 2>&1 | head -80
done
echo DONE
