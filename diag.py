"""Poll status printer GT2000 lewat Ethernet dan catat setiap perubahan.

Dipakai saat user memicu cek tinta: menangkap kode ERROR STATUS (2 byte,
byte rendah dulu) persis yang membuat printer menolak cartridge.

Pemakaian: py ethernet\diag.py [durasi_detik] [ip] [port]
"""
from __future__ import annotations
import socket, sys, time
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from gt2000 import build

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
IP = sys.argv[2] if len(sys.argv) > 2 else "192.168.1.8"
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8010

WORK = {0: "Ready", 1: "Print", 2: "SelfCheck", 3: "CleanHead", 4: "Spit",
        5: "Processing", 6: "FW-upgrade", 7: "SW-update"}
ESIMPLE = {0: "No error", 1: "Self-check fail", 2: "Realtime data late",
           3: "Head data overtime", 4: "No file", 5: "No font", 6: "File error",
           7: "Font/image", 8: "Char encoding", 9: "Memory", 10: "Missing static image",
           11: "SAME RFID chip (LOCK print head) -> reset via Loogal",
           12: "Save RFID to flash FAIL (print-head flash wrong)"}
FAM = {2: "print-file", 3: "controller", 4: "power", 5: "print-head-detect",
       6: "CARTRIDGE", 7: "head-comm", 8: "overspeed"}
CART = {1: "lock-number MISMATCH (change cartridge)", 2: "chip READ fail",
        3: "chip DAMAGED", 4: "reader MODULE fail", 5: "ink low", 6: "ink >130%"}


def decode_err(v: int) -> str:
    if v in ESIMPLE:
        return f"{v} = {ESIMPLE[v]}"
    hn = (v >> 12) & 0xF
    sub = v & 0xFF
    extra = (" " + CART[sub]) if (hn == 6 and sub in CART) else ""
    return f"0x{v:04x} {FAM.get(hn, '?')}{extra}"


def read_once(timeout: float = 2.0) -> bytes:
    d = b""
    for _ in range(2):
        try:
            s = socket.socket(); s.settimeout(timeout); s.connect((IP, PORT))
            s.sendall(build(0xA8)); d = s.recv(2048); s.close()
            if len(d) >= 2 and d[1] == 0x55:   # ditolak, coba lagi
                time.sleep(0.25); continue
            return d
        except Exception as e:
            return ("ERR:" + str(e)).encode()
    return d


def parse(d: bytes):
    if not d or d[0] != 0xCC or len(d) < 6:
        return None
    pl = d[3:3 + d[2]]
    if len(pl) < 5:
        return None
    return pl[2], pl[3] | (pl[4] << 8), pl   # work, error(2B), payload


def main() -> int:
    print(f"# poll {IP}:{PORT} selama {DUR:.0f}s — picu cek tinta sekarang", flush=True)
    t0 = time.time(); last = None
    while time.time() - t0 < DUR:
        d = read_once()
        p = parse(d)
        ts = f"{time.time()-t0:6.1f}s"
        if p:
            work, err, pl = p
            key = pl.hex()
            line = (f"{ts} work={WORK.get(work, hex(work))}  "
                    f"error={decode_err(err)}  raw={pl.hex()}")
        else:
            key = d.hex() if isinstance(d, (bytes, bytearray)) else str(d)
            line = f"{ts} (no-parse) {key}"
        if key != last:          # cetak hanya saat berubah
            print(line, flush=True); last = key
        time.sleep(0.6)
    print("# selesai", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
