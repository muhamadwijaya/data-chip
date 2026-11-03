"""Klien protokol Ethernet Gressler/GT2000 (UDP) — pustaka standar saja.

Paket perintah : AA | cmd | len | [params] | CRC8
Respons        : CC | cmd | len | [data]   | CRC8   (error-ack: CC 55 CRC8)
CRC8           : poly 0x31 (x8+x5+x4+1), init 0x00, MSB-first, atas semua byte.

Perintah aman read-only yang dipakai di sini: 0xA8 (Read status).
Jangan kirim A1/A3/A4/A5/A6 tanpa maksud jelas (memicu cetak/tinta/ubah setelan).
"""
from __future__ import annotations
import socket
import sys


def _crc8_table():
    tbl = []
    for b in range(256):
        c = b
        for _ in range(8):
            c = ((c << 1) ^ 0x31) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
        tbl.append(c)
    return tbl

CRC_TABLE = _crc8_table()


def crc8(data: bytes) -> int:
    c = 0
    for x in data:
        c = CRC_TABLE[c ^ x]
    return c


def build(cmd: int, params: bytes = b"") -> bytes:
    body = bytes([0xAA, cmd, len(params)]) + params
    return body + bytes([crc8(body)])


def send_recv(ip: str, port: int, packet: bytes, timeout: float = 3.0,
              tcp: bool = True) -> bytes | None:
    fam = socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM
    s = socket.socket(socket.AF_INET, fam)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.sendall(packet)
        try:
            return s.recv(2048)
        except socket.timeout:
            return None
    finally:
        s.close()


def dump(label: str, data: bytes) -> None:
    print(f"{label} ({len(data)} B): {data.hex()}")
    # cetak per-byte beroffset untuk interpretasi
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        print(f"   [{i:02d}] {hexs}")


def parse_status(data: bytes) -> None:
    if len(data) < 3:
        print("respons terlalu pendek"); return
    if data[0] != 0xCC:
        print(f"respons head bukan 0xCC: {data[0]:02x}"); return
    if data[1] == 0x55:
        print("ERROR-ACK (CC 55): perintah ditolak/CRC salah"); return
    cmd = data[1]; plen = data[2]
    payload = data[3:3+plen]
    crc_ok = (len(data) >= 4 + plen) and (data[3+plen] == crc8(data[:3+plen]))
    print(f"cmd=0x{cmd:02x} param_len={plen} crc_ok={crc_ok}")
    dump("status-payload", payload)


def main() -> int:
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.8"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8010
    pkt = build(0xA8)  # Read status
    print(f"-> {ip}:{port}  read-status: {pkt.hex()}")
    resp = send_recv(ip, port, pkt, timeout=3.0)
    if resp is None:
        print("(tidak ada balasan dalam 3 dtk pada port ini)")
        return 1
    dump("RESP", resp)
    parse_status(resp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
