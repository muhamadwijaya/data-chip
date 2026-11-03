"""Pacu printer agar MENCETAK TERUS sampai ambang re-verifikasi (~455),
supaya printer melakukan baca-penuh cartridge (secure-read + tulis state baru)
yang ditangkap sniff Proxmark. START sekali, JANGAN di-STOP di tengah.

Membaca aliran status yang DIDORONG printer (push tiap ~1s), parse per-frame
17-byte (CC A8 0D ... CRC). Pemakaian: py ethernet\drive.py [durasi_detik]
"""
from __future__ import annotations
import socket, time, sys
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from gt2000 import build

IP, PORT = "192.168.1.8", 8010
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 170.0
CART = {1: "lock MISMATCH", 2: "chip READ fail", 3: "chip DAMAGED",
        4: "reader MODULE fail", 5: "ink low", 6: "ink>130%"}
WORK = {0: "Ready", 1: "Print", 2: "SelfCheck", 3: "CleanHead"}

s = socket.socket(); s.settimeout(3.0)
try:
    s.connect((IP, PORT))
except Exception as e:
    print(f"[x] connect gagal: {e}"); sys.exit(1)
print("[ok] terhubung; STOP lalu START sekali, biarkan mencetak sampai re-verify", flush=True)

s.sendall(build(0xA2)); time.sleep(1.5)   # STOP/recover
try: s.recv(2048)
except Exception: pass
s.sendall(build(0xA1)); time.sleep(1.0)   # START sekali

buf = b""; t0 = time.time(); last = None; saw_error = False
while time.time() - t0 < DUR:
    try:
        data = s.recv(2048)
    except socket.timeout:
        continue
    except Exception:
        break
    if not data:
        break
    buf += data
    # ekstrak frame lengkap
    while len(buf) >= 3:
        if buf[0] != 0xCC:
            i = buf.find(0xCC)
            if i < 0:
                buf = b""; break
            buf = buf[i:]
            continue
        if buf[1] == 0x55:
            flen = 3
        else:
            if len(buf) < 3:
                break
            flen = 3 + buf[2] + 1
        if len(buf) < flen:
            break
        frame = buf[:flen]; buf = buf[flen:]
        if frame[1] == 0xA8 and len(frame) >= 8:
            pl = frame[3:3 + frame[2]]
            work = pl[2]; err = pl[3] | (pl[4] << 8); count = pl[5] | (pl[6] << 8)
            if (work, err) != last:
                es = "none" if err == 0 else (f"0x{err:04x} CARTRIDGE {CART.get(err & 0xFF,'?')}"
                                              if (err >> 12) == 6 else f"0x{err:04x}")
                print(f"{time.time()-t0:6.1f}s work={WORK.get(work,work)} err={es} count={count}",
                      flush=True)
                last = (work, err)
            if err != 0 and not saw_error:
                saw_error = True
                print(f"{time.time()-t0:6.1f}s >>> RE-VERIFY/error di count={count} "
                      f"— baca-penuh terjadi di sini, sniff menangkapnya", flush=True)

s.sendall(build(0xA2))   # tinggalkan Ready
s.close()
print(f"[ok] selesai (error terlihat: {saw_error})", flush=True)
