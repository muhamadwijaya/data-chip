"""Extract the 188-byte ink-applet file from the printer trace and diff before/after."""
from __future__ import annotations

from pathlib import Path

from trace_parse import parse, strip_iso_dep
from trace_analysis import Apdu

TRACE = Path(r"C:\Users\user\Downloads\Pasted text(20261026-040905).txt")


def main() -> None:
    frames = parse(TRACE)
    exchanges: list[tuple[float, Apdu, bytes]] = []
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
                exchanges.append((cmd.start / 13.56e6, c, r))
            cmd = None

    # Collect file reads by time, only the 4-chunk 188-byte reads.
    reads: list[tuple[float, bytes]] = []
    for i, (t, c, r) in enumerate(exchanges):
        if c.name() == "SELECT" and c.data == b"\x00\x04":
            data = b""
            ok = True
            for t2, c2, r2 in exchanges[i + 1:i + 5]:
                if c2.name() != "READ BINARY":
                    ok = False
                    break
                # response minus SW
                body = r2[:-2] if r2.endswith(b"\x90\x00") else r2
                data += body
            if ok and len(data) == 188:
                reads.append((t, data))
    print("file 0004 reads:")
    for t, d in reads:
        print(f"  t={t:.3f}s len={len(d)} last2={d[-2:].hex(' ')}")

    if len(reads) >= 2:
        before = reads[0][1]
        after = reads[-1][1]
        print("\nbyte diffs before -> after:")
        for i, (a, b) in enumerate(zip(before, after)):
            if a != b:
                print(f"  offset 0x{i:02X} ({i:3d}): {a:02X} -> {b:02X}")
        print("\nbefore:", before.hex(" "))
        print("after :", after.hex(" "))

    # Collect secure reads of 0006 / 0007.
    print("\nsecure reads:")
    for i, (t, c, r) in enumerate(exchanges):
        if c.name() == "SECURE READ":
            print(f"  t={t:.3f}s cmd={c.data.hex(' ')} resp={r.hex(' ')}")


if __name__ == "__main__":
    main()
