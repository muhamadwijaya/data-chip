"""Kendali printer GT2000 lewat Ethernet + baca status (pustaka standar).

Perintah: A1=start print, A2=stop print(/recover), A3=trigger, A8=read status.
START (A1) hanya membuat printer MASUK mode print-ready; tinta baru keluar bila
ada trigger sensor / A3 (TIDAK dikirim di sini). STOP (A2) kembali ke Ready dan
memulihkan dari error.

Pemakaian:
    py ethernet\control.py status
    py ethernet\control.py test      # stop -> start -> amati 18s -> stop
    py ethernet\control.py start|stop|trigger
"""
from __future__ import annotations
import socket, sys, time
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from gt2000 import build

IP, PORT = "192.168.1.8", 8010
WORK = {0: "Ready", 1: "Print", 2: "SelfCheck", 3: "CleanHead", 4: "Spit",
        5: "Processing", 6: "FW-upgrade", 7: "SW-update"}
CART = {1: "lock MISMATCH", 2: "chip READ fail", 3: "chip DAMAGED",
        4: "reader MODULE fail", 5: "ink low", 6: "ink>130%"}
CMDNAME = {0xA1: "START", 0xA2: "STOP", 0xA3: "TRIGGER", 0xA8: "STATUS"}


def sr(pkt: bytes, t: float = 2.0) -> bytes:
    d = b""
    for _ in range(3):
        try:
            s = socket.socket(); s.settimeout(t); s.connect((IP, PORT))
            s.sendall(pkt); d = s.recv(2048); s.close()
            if len(d) >= 2 and d[1] == 0x55:   # ditolak, coba lagi
                time.sleep(0.25); continue
            return d
        except Exception as e:
            return ("ERR:" + str(e)).encode()
    return d


def decode_status(d: bytes) -> str:
    if not d or d[0] != 0xCC or len(d) < 7:
        return f"raw={d.hex() if isinstance(d,(bytes,bytearray)) else d}"
    pl = d[3:3 + d[2]]
    work = pl[2]; err = pl[3] | (pl[4] << 8)
    hn = (err >> 12) & 0xF; sub = err & 0xFF
    if err == 0:
        es = "none"
    elif hn == 6:
        es = f"0x{err:04x} CARTRIDGE {CART.get(sub,'?')}"
    elif err <= 12:
        es = f"{err}"
    else:
        es = f"0x{err:04x}"
    return f"work={WORK.get(work,work)}  err={es}  raw={pl.hex()}"


def status() -> str:
    return decode_status(sr(build(0xA8)))


def send(cmd: int) -> str:
    d = sr(build(cmd))
    ack = "OK" if (len(d) >= 2 and d[0] == 0xCC and d[1] == cmd) else \
          ("REJECTED(CC55)" if (len(d) >= 2 and d[1] == 0x55) else "?")
    return f"{CMDNAME.get(cmd,hex(cmd))} -> {d.hex()} [{ack}]"


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg == "status":
        print(status()); return 0
    if arg in ("start", "stop", "trigger"):
        print(send({"start": 0xA1, "stop": 0xA2, "trigger": 0xA3}[arg]))
        time.sleep(0.8); print(" ->", status()); return 0
    if arg == "test":
        print("baseline  :", status())
        print(send(0xA2)); time.sleep(1.2)       # stop/recover -> ready
        print("after stop:", status())
        print(send(0xA1))                          # start print
        for i in range(12):
            time.sleep(1.5)
            print(f"  t+{(i+1)*1.5:4.1f}s:", status())
        print(send(0xA2)); time.sleep(1.2)         # stop -> ready
        print("after stop:", status())
        return 0
    print("arg tak dikenal"); return 2


if __name__ == "__main__":
    raise SystemExit(main())
