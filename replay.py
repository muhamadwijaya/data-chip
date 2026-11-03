"""Replay ISO14443-4 EAJet/GT1000 untuk emulator Proxmark3 ``simaid``.

Printer memakai APDU ISO14443-4 (bukan MIFARE Classic).  Emulator harus
mengembalikan UID, ATS, FCI, isi file 0004/0003, dan respons secure read
file 0006/0007 yang direkam dari kartu asli.  Response MAC secure read
dihitung dari GET CHALLENGE, jadi nilai challenge harus sama dengan yang
direkam bersama response tersebut.

Modul ini hanya memakai pustaka standar Python.
"""

from __future__ import annotations

from dataclasses import dataclass

UID = "FE7EA17E"
ATS = "107880900220900000000000FE7EA17E"
AID = "45414A4554"  # ASCII "EAJET"

# File 0004: 188 byte, persis seperti yang dikembalikan kartu asli.
FILE0004 = {
    "A": "9e9f9ebfbfbfd81765f0bdfdbd529e979f971f1f9e8f0f96bfbfbfbf9e8fbfbf0f96bfbf1f96bfbf9fbfbfbf1e8fbfbf979ebfbf9e1e161f169e97bfbfbfbfbf1f1ebfbf1e1e979f97979f8fb5359bce13869f5716928b292a35ca81c3915348a442dca99e9f1e9f9e961f9f9f9f9f9e0f0f0f9f0f9f961f0f8f17161617179f9e9eed0fdded2da43d0f2ded0f1f17749eed74eda4a49e9e9e17bfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfa0a6",
    "B": "9e9f9ebfbfbfd81765f0bdfdbd529e979f971f1f9e8f0f96bfbfbfbf9e8fbfbf0f96bfbf1f96bfbf9fbfbfbf1e8fbfbf979ebfbf9e171f969e971ebfbfbfbfbf1f1ebfbf1e1e979f97979f8fb5359bce13869f5716928b292a35ca81c3915348a442dca99e9f1e9f9e961f9f9f9f9f9e0f0f0f9f0f9f961f0f8f17161617179f9e9eed0fdded2da43d0f2ded0f1f17749eed74eda4a49e9e9e17bfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbf28a6",
    "C": "9e9f9ebfbfbfd81765f0bdfdbd529e979f971f1f9e8f0f96bfbfbfbf9e8fbfbf0f96bfbf1f96bfbf9fbfbfbf1e8fbfbf979ebfbf9e171f969e971ebfbfbfbfbf1f97bfbf1e1e979f97979f8fb5359bce13869f5716928b292a35ca81c3915348a442dca99e9f1e9f9e961f9f9f9f9f9e0f0f0f9f0f9f961f0f8f17161617179f9e9eed0fdded2da43d0f2ded0f1f17749eed74eda4a49e9e9e17bfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfa1a6",
    # Hasil decode ROR2 dari dump MIFARE FE7EA17E (factory backup).
    "factory": "9e9f9ebfbfbfa2a4a29e1a22a29e9e979f971f1f9e8f0f96bfbfbfbf9e8fbfbf0f96bfbf1f96bfbf9fbfbfbf1e8fbfbf979ebfbf9f9f9f9f9f9f9f9f9f9f9f9f9fbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbf9e9f1e9f9e961f9f9f9f9f9e0f0f0f9f0f9f961f0f8f17161617179f9e9eed0fdded2da43d0f2ded0f1f17749eed74eda4a49e9e9e17bfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbf",
    # State ke-5 yang ditulis printer ke kartu asli pada sniff real_D5
    # (2026-10-27).  Tail 67 26.
    "E": "9e9f9ebfbfbfd81765f0bdfdbd529e979f971f1f9e8f0f96bfbfbfbf9e8fbfbf0f96bfbf1f96bfbf9fbfbfbf1e8fbfbf979ebfbf9e9f8f97170f1f16bfbfbfbf1f8fbfbf1e1e979f97979f8fb5359bce13869f5716928b292a35ca81c3915348a442dca99e9f1e9f9e961f9f9f9f9f9e0f0f0f9f0f9f961f0f8f17161617179f9e9eed0fdded2da43d0f2ded0f1f17749eed74eda4a49e9e9e17bfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbf6726",
    # Rantai state real_D5 dari awal sniff: S1 -> S2 -> S3 -> S4 -> E.
    # Tail masing-masing: e7 26, 6f 26, d7 26, 6e 26, 67 26.
    "S1": "9e9f9ebfbfbfd81765f0bdfdbd529e979f971f1f9e8f0f96bfbfbfbf9e8fbfbf0f96bfbf1f96bfbf9fbfbfbf1e8fbfbf979ebfbf1f969e9e169f0f8fbfbfbfbf1f8fbfbf1e1e979f97979f8fb5359bce13869f5716928b292a35ca81c3915348a442dca99e9f1e9f9e961f9f9f9f9f9e0f0f0f9f0f9f961f0f8f17161617179f9e9eed0fdded2da43d0f2ded0f1f17749eed74eda4a49e9e9e17bfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfe726",
    "S2": "9e9f9ebfbfbfd81765f0bdfdbd529e979f971f1f9e8f0f96bfbfbfbf9e8fbfbf0f96bfbf1f96bfbf9fbfbfbf1e8fbfbf979ebfbf1f969e1617961e9ebfbfbfbf1f8fbfbf1e1e979f97979f8fb5359bce13869f5716928b292a35ca81c3915348a442dca99e9f1e9f9e961f9f9f9f9f9e0f0f0f9f0f9f961f0f8f17161617179f9e9eed0fdded2da43d0f2ded0f1f17749eed74eda4a49e9e9e17bfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbf6f26",
    "S3": "9e9f9ebfbfbfd81765f0bdfdbd529e979f971f1f9e8f0f96bfbfbfbf9e8fbfbf0f96bfbf1f96bfbf9fbfbfbf1e8fbfbf979ebfbf1f16160f961e9697bfbfbfbf1f8fbfbf1e1e979f97979f8fb5359bce13869f5716928b292a35ca81c3915348a442dca99e9f1e9f9e961f9f9f9f9f9e0f0f0f9f0f9f961f0f8f17161617179f9e9eed0fdded2da43d0f2ded0f1f17749eed74eda4a49e9e9e17bfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfd726",
    "S4": "9e9f9ebfbfbfd81765f0bdfdbd529e979f971f1f9e8f0f96bfbfbfbf9e8fbfbf0f96bfbf1f96bfbf9fbfbfbf1e8fbfbf979ebfbf1f0f1e9e171f8f17bfbfbfbf1f8fbfbf1e1e979f97979f8fb5359bce13869f5716928b292a35ca81c3915348a442dca99e9f1e9f9e961f9f9f9f9f9e0f0f0f9f0f9f961f0f8f17161617179f9e9eed0fdded2da43d0f2ded0f1f17749eed74eda4a49e9e9e17bfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbfbf6e26",
}

FILE0003_OLD = "33333430343430381800323033303236323337313732342020202020757ddb05"
FILE0003_NEW = "33333430343430381800323033303236323531363234332020202020757dd805"

FILE0003 = {
    "A": FILE0003_OLD,
    "B": FILE0003_NEW,
    "C": FILE0003_NEW,
    "factory": FILE0003_NEW,
    # Sniff real_D5: file 0003 state terakhir.
    "E": "33333430343430381800323033303236323038343539313720202020757df505",
    # file 0003 untuk rantai S1..S4 (real_D5).
    "S1": "33333430343430381800323033303236313632323730393820202020757df405",
    "S2": "33333430343430381800323033303236313632373536333220202020757df105",
    "S3": "33333430343430381800323033303236313737393633363420202020757dfc05",
    "S4": "33333430343430381800323033303236313933323531383520202020757df305",
}

# 88 byte = respons secure read file 0006 (44) + file 0007 (44).
SECURE = {
    "A": (
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f12254f94456a05a78f9f40824db244a8a01837e1dd06"
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f12254f94456a05a78f9f40824db244a8a01854e832b6"
    ),
    "B": (
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f1226499e317af4a78f9f40824db244a8df18a387b6a5"
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f1226499e317af4a78f9f40824db244a8df1878b0373b"
    ),
    "C": (
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f1226499e317af4a78f9f40824dba44a820185e327b97"
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f1226499e317af4a78f9f40824dba44a820187a4854ff"
    ),
    "E": (
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f12a3509a3da2d48a8f9f40824dda44a86818cda9f666"
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f12a3509a3da2d48a8f9f40824dda44a86818f6706da0"
    ),
    # Rantai S1..S4: 40 byte data + 4 byte response MAC per file.
    "S1": (
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70fd1a64a96455a55aa8f9f40824dda44a828189de904fa"
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70fd1a64a96455a55aa8f9f40824dda44a8281829a0910f"
    ),
    "S2": (
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70fd1a64aa03d8af4e98f9f40824dda44a8671816603050"
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70fd1a64aa03d8af4e98f9f40824dda44a867183066dd1b"
    ),
    "S3": (
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70fd1274fa44172252a8f9f40824dda44a82a189d2ab902"
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70fd1274fa44172252a8f9f40824dda44a82a186525379a"
    ),
    "S4": (
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70fd1284b963d62454a8f9f40824dda44a8e718fc1d7ad2"
        "3368d89983278d9f75f0e5d3b70f83877b01ed14f70fd1284b963d62454a8f9f40824dda44a8e718a2fad055"
    ),
}

# GET CHALLENGE yang terekam bersama response MAC di trace_full_new.txt.
CHALLENGE = {
    "A": ("691d4fc3", "1a6ace1f"),
    "B": ("96bf9a55", "877e5087"),
    "C": ("b9be715f", "a61d5a69"),
    "factory": ("b9be715f", "a61d5a69"),
    "E": ("5ce27f48", "41a9aefb"),
    # GET CHALLENGE untuk tiap secure read pada rantai real_D5.
    "S1": ("6896080f", "9f8df552"),
    "S2": ("7de780ea", "9f6399f2"),
    "S3": ("73cf4916", "951d1c8c"),
    "S4": ("a31d4870", "1550d1f1"),
}

DESCRIPTION = {
    "A": "state awal trace: file 0004 A0 A6, file 0003 20260317, secure a018",
    "B": "setelah cetak 1: file 0004 28 A6, file 0003 20260516, secure df18",
    "C": "setelah cetak 2: file 0004 A1 A6, file 0003 20260516, secure 2018",
    "factory": "file 0004 factory (ROR2 dump MIFARE), file 0003 baru, secure set C",
    "E": "sniff real_D5 (2026-10-27): file 0004 67 26, file 0003 20260845, secure a86818",
    "S1": "rantai real_D5 awal: file 0004 e7 26, file 0003 20261622, secure a82818",
    "S2": "rantai real_D5 ke-2: file 0004 6f 26, file 0003 20261627, secure a86718",
    "S3": "rantai real_D5 ke-3: file 0004 d7 26, file 0003 20261779, secure a82a18",
    "S4": "rantai real_D5 ke-4: file 0004 6e 26, file 0003 20261932, secure a8e718",
}


@dataclass(frozen=True)
class ReplaySet:
    """Satu state kartu yang bisa diputar ulang oleh emulator."""

    name: str
    description: str
    file0004: bytes
    file0003: bytes
    secure: bytes
    challenge_0006: bytes
    challenge_0007: bytes
    uid: str = UID
    ats: str = ATS
    aid: str = AID
    # 0 = strict replay, 1 = keep unknown file0004 but not secure data,
    # 2 = store every write (old dynamic behaviour), 3 = reject unknown writes,
    # 4 = keep unknown file0004/file0003 but not secure data.
    mode: int = 0

    @property
    def selectaid_response(self) -> bytes:
        return self.file0004 + self.file0003

    @property
    def getdata_response(self) -> bytes:
        # A non-zero mode is appended as a 89th byte.  The firmware only uses
        # the first 88 bytes for the secure image, so mode 0 stays compatible
        # with the original 88-byte command.
        if self.mode:
            return self.secure + bytes([self.mode])
        return self.secure

    @property
    def firmware_set(self) -> str:
        return self.name.upper()

    def simaid_command(self) -> str:
        """Perintah client Proxmark3 untuk menjalankan emulator state ini."""
        return (
            f"hf 14a simaid -t 4 -u {self.uid} --ats {self.ats} --aid {self.aid} "
            f"--selectaid_response {self.selectaid_response.hex()} "
            f"--getdata_response {self.getdata_response.hex()}"
        )

    def summary(self) -> dict[str, str]:
        return {
            "set": self.name,
            "description": self.description,
            "uid": self.uid,
            "file0004": self.file0004.hex(),
            "file0003": self.file0003.hex(),
            "secure": self.secure.hex(),
            "challenge_0006": self.challenge_0006.hex(),
            "challenge_0007": self.challenge_0007.hex(),
            "mode": str(self.mode),
            "firmware_set": self.firmware_set,
            "command": self.simaid_command(),
        }


def _build(name: str) -> ReplaySet:
    file0004 = bytes.fromhex(FILE0004[name])
    file0003 = bytes.fromhex(FILE0003[name])
    secure = bytes.fromhex(SECURE["C" if name == "factory" else name])
    ch6, ch7 = (bytes.fromhex(x) for x in CHALLENGE[name])
    if len(file0004) != 188:
        raise ValueError(f"file0004 {name}: {len(file0004)} byte, harus 188")
    if len(file0003) != 32:
        raise ValueError(f"file0003 {name}: {len(file0003)} byte, harus 32")
    if len(secure) != 88:
        raise ValueError(f"secure {name}: {len(secure)} byte, harus 88")
    if len(ch6) != 4 or len(ch7) != 4:
        raise ValueError(f"challenge {name}: harus 4 byte")
    return ReplaySet(
        name=name,
        description=DESCRIPTION[name],
        file0004=file0004,
        file0003=file0003,
        secure=secure,
        challenge_0006=ch6,
        challenge_0007=ch7,
    )


SETS: dict[str, ReplaySet] = {name: _build(name) for name in DESCRIPTION}


def get_set(name: str) -> ReplaySet:
    try:
        return SETS[name]
    except KeyError as exc:
        raise ValueError(
            f"set tidak dikenal: {name}. Pilihan: {', '.join(sorted(SETS))}"
        ) from exc


def format_table() -> str:
    lines = ["Set       Firmware   Keterangan"]
    lines.append("-" * 72)
    for name in sorted(SETS):
        s = SETS[name]
        lines.append(f"{name:8s}  {s.firmware_set:9s}  {s.description}")
    return "\n".join(lines)
