"""Auto-recover printer GT2000 saat re-verifikasi cartridge gagal (0x6xxx).

Klon (mis. set C) dicetak normal, tapi printer re-verifikasi cartridge tiap
~400+ cetak dan gagal (0x6102). Perintah STOP (A2) mengembalikan printer dari
error ke Ready (per manual), lalu START (A1) melanjutkan cetak. Skrip ini
memantau status lewat SATU koneksi persisten dan otomatis recover setiap kali
muncul error cartridge — supaya cetak jalan terus tanpa power-cycle manual.

Pemakaian: py ethernet\autorecover.py [durasi_detik] [ip] [port]
Ctrl-C untuk berhenti. Kirim STOP bersih saat keluar.
"""
from __future__ import annotations
import socket, sys, time
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from gt2000 import build

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 3600.0
IP = sys.argv[2] if len(sys.argv) > 2 else "192.168.1.8"
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8010
WORK = {0: "Ready", 1: "Print", 2: "SelfCheck", 3: "CleanHead", 4: "Spit",
        5: "Processing", 6: "FW-up", 7: "SW-up"}
CART = {1: "lock MISMATCH", 2: "chip READ fail", 3: "chip DAMAGED",
        4: "reader MODULE fail", 5: "ink low", 6: "ink>130%"}


def parse(d: bytes):
    if not d or d[0] != 0xCC or d[1] != 0xA8 or len(d) < 7:
        return None
    pl = d[3:3 + d[2]]
    if len(pl) < 7:
        return None
    work = pl[2]
    err = pl[3] | (pl[4] << 8)
    count = pl[5] | (pl[6] << 8)      # print counter
    return work, err, count, pl


def main() -> int:
    s = socket.socket(); s.settimeout(5.0)
    try:
        s.connect((IP, PORT))
    except Exception as e:
        print(f"[x] connect gagal: {e} (tutup NetAssist/Loogal dulu, atau power-cycle)")
        return 1
    print(f"[ok] auto-recover aktif ke {IP}:{PORT}, durasi {DUR:.0f}s", flush=True)

    def cmd(c: int) -> bytes:
        try:
            s.sendall(build(c)); return s.recv(2048)
        except Exception:
            return b""

    print("[*] START awal untuk memulai cetak (printer ~12s jadi ready)...", flush=True)
    cmd(0xA1); time.sleep(12.0)
    t0 = time.time(); last = None; recoveries = 0
    last_recover = 0.0; fast_recovers = 0
    while time.time() - t0 < DUR:
        d = cmd(0xA8)
        p = parse(d)
        ts = time.strftime("%H:%M:%S")
        if not p:
            if d[:2] != b"\xcc\xa8":
                print(f"{ts} resp aneh: {d.hex() if d else '(timeout)'}", flush=True)
            time.sleep(1.0); continue
        work, err, count, pl = p
        hn = (err >> 12) & 0xF; sub = err & 0xFF
        key = (work, err)
        if key != last:
            es = "none" if err == 0 else (f"0x{err:04x} CARTRIDGE {CART.get(sub,'?')}"
                                          if hn == 6 else f"0x{err:04x}")
            print(f"{ts} work={WORK.get(work,work)} err={es} count={count}", flush=True)
            last = key
        # auto-recover pada error cartridge (0x6xxx) atau error apa pun != 0
        if err != 0:
            now = time.time()
            recoveries += 1
            fast_recovers = fast_recovers + 1 if (now - last_recover < 15) else 0
            last_recover = now
            print(f"{ts} >>> RECOVER #{recoveries}: STOP(A2)->START(A1) "
                  f"(count={count}, err=0x{err:04x})", flush=True)
            cmd(0xA2); time.sleep(2.0)            # STOP -> recover ke Ready
            cmd(0xA1); time.sleep(12.0)           # printer ~12s jadi ready setelah protokol
            last = None                           # paksa cetak status berikutnya
            if fast_recovers >= 3:
                print(f"{ts} [!] 3x recover <15s berturut — STOP tidak mereset "
                      f"re-verifikasi; perlu kunci DES / power-cycle. Berhenti.", flush=True)
                break
        time.sleep(1.0)

    cmd(0xA2)   # tinggalkan printer dalam keadaan Ready
    s.close()
    print(f"[ok] selesai. total recover: {recoveries}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
