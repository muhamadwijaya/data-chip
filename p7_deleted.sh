#!/usr/bin/env bash
set +e
P=/var/tmp/p7_sparse.img
for ino in 65537 65546 65580 65585 114689 114690 114692 114694 114695 114696; do
  echo "########## inode $ino ##########"
  debugfs -R "stat <$ino>" "$P" 2>&1 | head -35
  rm -f /var/tmp/del_$ino.bin
  debugfs -R "dump <$ino> /var/tmp/del_$ino.bin" "$P" 2>&1 | head -3
  if [ -f /var/tmp/del_$ino.bin ]; then
    ls -l /var/tmp/del_$ino.bin
    echo "--- strings ---"
    strings -n 3 /var/tmp/del_$ino.bin | head -30
    echo "--- hex ---"
    xxd -l 256 /var/tmp/del_$ino.bin
  fi
done
echo DONE
