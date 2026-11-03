"""Klien GT2000 Ethernet dengan SATU koneksi TCP persisten (pustaka standar).

Printer melayani satu klien dan tidak menutup koneksi dengan cepat; membuka
koneksi baru per perintah menumpuk socket half-open (FIN_WAIT_2) dan membuat
server printer macet. Jadi: connect SEKALI, pakai ulang untuk semua perintah.

Pemakaian: py ethernet\session.py [ip] [port]
Urutan uji: status -> STOP -> status -> START -> status x8 -> STOP -> status.
"""
from __future__ import annotations
import socket, sys, time
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from gt2000 import build

IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.8"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8010
WORK = {0: "Ready", 1: "Print", 2: "SelfCheck", 3: "CleanHead", 4: "Spit",
        5: "Processing", 6: "FW-up", 7: "SW-up"}
CART = {1: "lock MISMATCH", 2: "chip READ fail", 3: "chip DAMAGED",
        4: "reader MODULE fail", 5: "ink low", 6: "ink>130%"}


def decode(d: bytes) -> str:
    if not d or d[0] != 0xCC or len(d) < 7:
        if d and d[:2] == b"\xcc\x55":
            return "ERROR-ACK(CC55)"
        return ""
    pl = d[3:3 + d[2]]
    if len(pl) < 5:
        return ""
    work = pl[2]; err = pl[3] | (pl[4] << 8)
    hn = (err >> 12) & 0xF; sub = err & 0xFF
    if err == 0:
        es = "none"
    elif hn == 6:
        es = f"0x{err:04x} CARTRIDGE {CART.get(sub,'?')}"
    else:
        es = f"0x{err:04x}" if err > 12 else str(err)
    return f"work={WORK.get(work,work)} err={es} raw={pl.hex()}"


def main() -> int:
    s = socket.socket()
    s.settimeout(5.0)
    try:
        s.connect((IP, PORT))
    except Exception as e:
        print(f"[x] connect gagal: {e}  (printer mungkin masih macet / perlu power-cycle)")
        return 1
    print(f"[ok] koneksi persisten ke {IP}:{PORT}")

    def send(cmd: int, label: str):
        try:
            s.sendall(build(cmd))
            d = s.recv(2048)
        except socket.timeout:
            print(f"  {label:14s} (timeout)"); return b""
        except Exception as e:
            print(f"  {label:14s} ERR {e}"); return b""
        print(f"  {label:14s} {decode(d) or d.hex()}")
        return d

    send(0xA8, "status")
    send(0xA2, "STOP")
    time.sleep(1.0); send(0xA8, "after-stop")
    send(0xA1, "START")
    for i in range(8):
        time.sleep(1.5); send(0xA8, f"t+{(i+1)*1.5:.1f}s")
    send(0xA2, "STOP")
    time.sleep(1.0); send(0xA8, "after-stop")
    s.close()
    print("[ok] selesai, koneksi ditutup bersih")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
