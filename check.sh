#!/usr/bin/env bash
set +e
sudo -n true 2>&1
echo "sudo_exit=$?"
ps aux | grep -E 'mount|sudo' | grep -v grep | head
echo "mountpoints:"
mount | grep -E 'rfs|rootfs' | head
