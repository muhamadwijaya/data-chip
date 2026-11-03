#!/usr/bin/env bash
set +e
cd '/mnt/o/tij gt 1000'
echo '=== update GT1000.rar ==='
7z l 'update GT1000.rar' 2>&1 | head -100
echo '=== package.zip ==='
7z l 'package.zip' 2>&1 | head -60
echo '=== tij gt 1000.zip ==='
7z l 'tij gt 1000.zip' 2>&1 | head -100
