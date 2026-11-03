"""Extract every 188-byte file image from the trace (read groups and write groups)."""
from __future__ import annotations

from pathlib import Path

from trace_parse import parse, strip_iso_dep
from trace_analysis import Apdu

TRACE = Path(r"C:\Users\user\Downloads\Pasted text(20261026-040905).txt")


def main() -> None:
    frames = parse(TRACE)
    ex: list[tuple[float, Apdu, bytes]] = []
    cmd = None
    for f in frames:
        if f.src == "Rdr":
            if f.data[:1] in (b"\x52", b"\x93", b"\xe0", b"\x50"):
                cmd = None
                continue
            cmd = f
        elif f.src == "Tag" and cmd is not None:
            c = Apdu.parse(strip_iso_dep(cmd.data))
            r = strip_iso_dep(f.data)
            if c:
                ex.append((cmd.start / 13.56e6, c, r))
            cmd = None

    # Groups of consecutive READ BINARY with Le 0x30,0x30,0x30,0x2c
    print("READ groups:")
    i = 0
    while i < len(ex):
        t, c, r = ex[i]
        if c.name() == "READ BINARY" and c.le in (0x30, 0x2C):
            group = []
            j = i
            while j < len(ex) and ex[j][1].name() == "READ BINARY":
                group.append(ex[j])
                j += 1
            data = b"".join(r[:-2] if r.endswith(b"\x90\x00") else r for _, _, r in group)
            if len(data) == 188:
                print(f"  t={t:.3f}s chunks={len(group)} last2={data[-2:].hex(' ')}")
                print("   ", data.hex(" "))
            i = j
        else:
            i += 1

    # Groups of consecutive UPDATE BINARY (0x28 bytes each)
    print("\nWRITE groups:")
    i = 0
    while i < len(ex):
        t, c, r = ex[i]
        if c.name() == "UPDATE BINARY":
            group = []
            j = i
            while j < len(ex) and ex[j][1].name() == "UPDATE BINARY":
                group.append(ex[j])
                j += 1
            data = b"".join(c2.data for _, c2, _ in group)
            print(f"  t={t:.3f}s chunks={len(group)} len={len(data)} last2={data[-2:].hex(' ')}")
            print("   ", data.hex(" "))
            i = j
        else:
            i += 1


if __name__ == "__main__":
    main()
