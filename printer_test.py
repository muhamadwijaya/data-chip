#!/usr/bin/env python3
"""Uji emulator EAJet/GT1000 pada Proxmark3.

Script ini menjalankan `hf 14a simaid` dengan state yang direkam dari trace
printer.  Firmware Proxmark3 harus sudah dipatch dengan eajet_sim.c dan
di-build untuk set yang sama (lihat proxmark_patch/build_flash.py).

Contoh:
    py printer_test.py --list
    py printer_test.py --set C --seconds 120
    py printer_test.py --set factory --seconds 120 --debug
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

# Pastikan paket gtink ditemukan walau script dijalankan dari folder lain.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gtink.replay import SETS as REPLAY_SETS  # noqa: E402

CLIENT = Path(r"C:\ProxSpace\pm3\proxmark3\client\proxmark3.exe")
MINGW = Path(r"C:\ProxSpace\msys2\mingw64\bin")

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def build_command(set_name: str, mode: int = 0) -> str:
    replay_set = REPLAY_SETS[set_name]
    if mode:
        replay_set = replace(replay_set, mode=mode)
    return replay_set.simaid_command()


def find_port(default: str = "COM11") -> str:
    """Kembalikan COM11 bila ada, kalau tidak cari port Proxmark via PowerShell."""
    try:
        import serial.tools.list_ports  # type: ignore
    except Exception:
        return default
    for p in serial.tools.list_ports.comports():
        if (p.vid, p.pid) == (0x9AC4, 0x4B8F):
            return p.device
    return default


def run(cmd: str, port: str, seconds: int, debug: bool, log_path: Path) -> int:
    if not CLIENT.exists():
        print(f"Client tidak ditemukan: {CLIENT}", file=sys.stderr)
        return 2

    args = [str(CLIENT), "-p", port]
    if debug:
        args += ["-d", "2"]
    args += ["-c", cmd]

    env = os.environ.copy()
    env["PATH"] = str(MINGW) + ";" + env.get("PATH", "")

    print(f"Port       : {port}")
    print(f"Perintah   : {cmd}")
    print(f"Log        : {log_path}")
    print("Menjalankan emulator. Picu pengecekan tinta di printer sekarang...")
    sys.stdout.flush()

    started = time.time()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write(f"# port={port} debug={debug}\n")
        log.write(f"# cmd={cmd}\n\n")
        # stdin stays an open pipe so the client's "press enter to abort"
        # check does not see EOF and exit immediately.
        proc = subprocess.Popen(
            args,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        try:
            proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            log.write("\n# [timeout, client dihentikan]\n")

    elapsed = time.time() - started
    print(f"Selesai setelah {elapsed:.1f} detik (exit={proc.returncode}).")
    print(f"Log lengkap: {log_path}")

    # Tampilkan baris yang relevan saja.
    text = strip_ansi(log_path.read_text(encoding="utf-8", errors="replace"))
    keywords = ("APDU", "READ file", "SECREAD", "Emulating", "Press", "error",
                "Error", "ERROR", "abort", "Abort", "timeout", "Timeout")
    shown = 0
    for line in text.splitlines():
        if any(k in line for k in keywords):
            print(line)
            shown += 1
            if shown >= 80:
                break
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--set",
        choices=sorted(REPLAY_SETS),
        default="C",
        help="state yang diputar",
    )
    ap.add_argument("--port", default=None, help="port serial Proxmark3 (default: auto/COM11)")
    ap.add_argument("--seconds", type=int, default=120, help="lama emulator berjalan")
    ap.add_argument("--debug", action="store_true", help="aktifkan log APDU dari firmware (-d 2)")
    ap.add_argument(
        "--mode",
        type=int,
        choices=(0, 1, 2, 3, 4),
        default=0,
        help="0=abaikan tulis asing, 1=simpan file0004 asing saja, "
             "2=simpan semua (lama), 3=tolak tulis asing, "
             "4=simpan file0004/file0003, secure tetap",
    )
    ap.add_argument("--dry-run", action="store_true", help="hanya cetak perintah")
    ap.add_argument("--list", action="store_true", help="daftar set yang tersedia")
    args = ap.parse_args()

    if args.list:
        for name in sorted(REPLAY_SETS):
            print(f"{name:8s} {REPLAY_SETS[name].description}")
        return 0

    cmd = build_command(args.set, args.mode)
    if args.dry_run:
        print(cmd)
        return 0

    port = args.port or find_port()
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"printer_{args.set}_{time.strftime('%Y%m%d_%H%M%S')}.log"
    return run(cmd, port, args.seconds, args.debug, log_path)


if __name__ == "__main__":
    raise SystemExit(main())
