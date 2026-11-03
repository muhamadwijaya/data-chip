#!/usr/bin/env python3
"""Splice, build, and optionally flash the EAJet Proxmark3 emulator for a set.

Contoh:
    py proxmark_patch\\build_flash.py --set C
    py proxmark_patch\\build_flash.py --set A --flash
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPLICE = ROOT / "splice_sim.py"
BUILD_DIR = Path(r"C:\ProxSpace\pm3\proxmark3")
MSYS = Path(r"C:\ProxSpace\msys2\usr\bin\bash.exe")
CLIENT = Path(r"C:\ProxSpace\pm3\proxmark3\client\proxmark3.exe")
ELF = BUILD_DIR / "armsrc" / "obj" / "fullimage.elf"


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, **kw)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", choices=("A", "B", "C", "FACTORY", "E", "S1", "S2", "S3", "S4"), default="C")
    ap.add_argument("--flash", action="store_true", help="flash setelah build")
    ap.add_argument("--port", default="COM11")
    args = ap.parse_args()

    # 1. splice
    r = run([sys.executable, str(SPLICE), "--set", args.set], check=False)
    if r.returncode != 0:
        return r.returncode

    # 2. build
    r = run([str(MSYS), "-lc",
             "export PATH=/mingw64/bin:/usr/bin:/bin; cd /pm3/proxmark3 && make -C armsrc"],
            check=False)
    if r.returncode != 0:
        return r.returncode

    if not ELF.exists():
        print("Build gagal: ELF tidak ditemukan", file=sys.stderr)
        return 1
    print("Build OK:", ELF)

    if not args.flash:
        print("Lewati flash (gunakan --flash).")
        return 0

    # 3. flash
    r = run([str(CLIENT), "-p", args.port, "--flash",
             "--image", str(ELF), "--force"], check=False)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
