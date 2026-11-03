from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


CARD_SIZE = 1024
BLOCK_SIZE = 16
BLOCK_COUNT = 64
SECTOR_COUNT = 16
SECTOR_BLOCK_COUNT = 4

DEFAULT_KEY = bytes.fromhex("FFFFFFFFFFFF")
DEFAULT_ACCESS = bytes.fromhex("FF078069")
DEFAULT_ACCESS_BITS = DEFAULT_ACCESS[:3]
DEFAULT_GPB = 0x69

# Chip ini memakai dua salinan record yang masing-masing berisi:
#   12 blok payload (192 byte) + 10 blok tail (160 byte) = 22 blok data
# Record pertama dimulai di blok 4, record kedua di blok 33.
# Blok trailer (7, 11, 15, ...) tidak termasuk data record.
RECORD_STARTS = (4, 33)
RECORD_BLOCK_COUNT = 29
PAYLOAD_BLOCK_COUNT = 12
TAIL_BLOCK_COUNT = 10
PAYLOAD_SIZE = PAYLOAD_BLOCK_COUNT * BLOCK_SIZE
TAIL_SIZE = TAIL_BLOCK_COUNT * BLOCK_SIZE

# Counter ada di blok 29 dan 58, offset 10, 16-bit little-endian.
COUNTER_BLOCKS = (29, 58)
COUNTER_OFFSET = 10
COUNTER_SIZE = 2
COUNTER_HEADER_SIZE = 10

# Index counter di dalam daftar 10 blok tail.
TAIL_COUNTER_INDEX = 7
TAIL_COUNTER_OFFSET = TAIL_COUNTER_INDEX * BLOCK_SIZE + COUNTER_OFFSET

# Nilai-nilai yang ditemukan pada empat dump.
KNOWN_COUNTERS = {
    "1EB75C2C": 64016,
    "5EEFAB9B": 64606,
    "BE8AAA9B": 12107,
    "FE7EA17E": 64516,
}
KNOWN_FULL_COUNTER = 65000
MAX_COUNTER = 0xFFFF


class CardError(ValueError):
    """Kesalahan saat membaca atau memproses dump kartu."""


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.message}"


def _as_path(path: str | Path | None) -> Path | None:
    return Path(path) if path is not None else None


def _hex_bytes(value: str, expected_len: int, what: str) -> bytes:
    text = re.sub(r"[\s:_-]", "", value or "")
    if len(text) != expected_len * 2:
        raise CardError(f"{what}: butuh {expected_len} byte, dapat {len(text) // 2} byte")
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise CardError(f"{what}: hex tidak valid") from exc


class Card:
    """Satu image MIFARE Classic 1K berukuran 1024 byte."""

    def __init__(
        self,
        data: bytes | bytearray | memoryview,
        source: str | Path | None = None,
    ) -> None:
        raw = bytes(data)
        if len(raw) != CARD_SIZE:
            raise CardError(
                f"Ukuran dump harus {CARD_SIZE} byte, bukan {len(raw)} byte"
            )
        self.data = bytearray(raw)
        self.source = _as_path(source)

    # ------------------------------------------------------------------
    # Konstruksi / penyimpanan
    # ------------------------------------------------------------------
    @classmethod
    def from_bytes(
        cls, data: bytes | bytearray | memoryview, source: str | Path | None = None
    ) -> "Card":
        return cls(data, source)

    @classmethod
    def from_file(cls, path: str | Path) -> "Card":
        p = Path(path)
        if not p.exists():
            raise CardError(f"File tidak ditemukan: {p}")
        suffix = p.suffix.lower()
        if suffix == ".bin":
            raw = p.read_bytes()
            if len(raw) != CARD_SIZE:
                raise CardError(
                    f"{p.name}: ukuran {len(raw)} byte, seharusnya {CARD_SIZE} byte"
                )
            return cls(raw, p)
        if suffix == ".json":
            return cls._from_json(p)
        if suffix == ".eml":
            return cls._from_eml(p)
        raise CardError(
            f"Format tidak didukung: {p.suffix or '(tanpa ekstensi)'} "
            "(pakai .bin, .json, atau .eml)"
        )

    @classmethod
    def _from_json(cls, path: Path) -> "Card":
        try:
            obj = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CardError(f"{path.name}: JSON tidak valid: {exc}") from exc

        blocks_obj = obj.get("blocks") if isinstance(obj, dict) else None
        if blocks_obj is None and isinstance(obj, dict) and "sectors" in obj:
            # Beberapa versi Proxmark3 menyimpan blocks di dalam sectors.
            blocks_obj = {}
            for sector in obj.get("sectors", []):
                for block in sector.get("blocks", []):
                    if isinstance(block, dict) and "block" in block and "data" in block:
                        blocks_obj[str(block["block"])] = block["data"]
        if not isinstance(blocks_obj, dict):
            raise CardError(f"{path.name}: tidak menemukan objek 'blocks'")

        raw = bytearray(CARD_SIZE)
        found = 0
        for index in range(BLOCK_COUNT):
            value = blocks_obj.get(str(index))
            if value is None:
                value = blocks_obj.get(index)  # type: ignore[arg-type]
            if value is None:
                continue
            block = _hex_bytes(str(value), BLOCK_SIZE, f"{path.name} blok {index}")
            raw[index * BLOCK_SIZE : (index + 1) * BLOCK_SIZE] = block
            found += 1
        if found != BLOCK_COUNT:
            raise CardError(
                f"{path.name}: hanya {found} dari {BLOCK_COUNT} blok yang ditemukan"
            )
        return cls(raw, path)

    @classmethod
    def _from_eml(cls, path: Path) -> "Card":
        """Baca format .eml Proxmark3 (satu blok 16 byte per baris)."""
        raw = bytearray()
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1
        ):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            compact = re.sub(r"[\s:_-]", "", line)
            if len(compact) != BLOCK_SIZE * 2:
                raise CardError(
                    f"{path.name}:{line_no}: baris .eml harus 16 byte hex"
                )
            try:
                raw.extend(bytes.fromhex(compact))
            except ValueError as exc:
                raise CardError(
                    f"{path.name}:{line_no}: hex tidak valid"
                ) from exc
        if len(raw) != CARD_SIZE:
            raise CardError(
                f"{path.name}: ukuran .eml {len(raw)} byte, seharusnya {CARD_SIZE}"
            )
        return cls(raw, path)

    def copy(self) -> "Card":
        return Card(bytes(self.data), self.source)

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.data)
        return p

    def save_json(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.to_json_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return p

    def save_eml(self, path: str | Path) -> Path:
        """Simpan format .eml Proxmark3 (64 baris, satu blok per baris)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            "\n".join(self.block(index).hex().upper() for index in range(BLOCK_COUNT))
            + "\n",
            encoding="utf-8",
        )
        return p

    def to_json_dict(self) -> dict:
        return {
            "Created": "gtink",
            "FileType": "mfc v2",
            "Card": {
                "UID": self.uid_hex,
                "ATQA": self.atqa_hex,
                "SAK": f"{self.sak:02X}",
            },
            "blocks": {
                str(index): self.block(index).hex().upper()
                for index in range(BLOCK_COUNT)
            },
        }

    # ------------------------------------------------------------------
    # Blok dasar
    # ------------------------------------------------------------------
    def block(self, index: int) -> bytes:
        if not 0 <= index < BLOCK_COUNT:
            raise IndexError(f"Blok di luar jangkauan: {index}")
        return bytes(self.data[index * BLOCK_SIZE : (index + 1) * BLOCK_SIZE])

    def set_block(self, index: int, value: bytes) -> None:
        if not 0 <= index < BLOCK_COUNT:
            raise IndexError(f"Blok di luar jangkauan: {index}")
        if len(value) != BLOCK_SIZE:
            raise CardError(f"Blok {index} harus 16 byte")
        self.data[index * BLOCK_SIZE : (index + 1) * BLOCK_SIZE] = value

    def blocks(self) -> Iterator[bytes]:
        for index in range(BLOCK_COUNT):
            yield self.block(index)

    @staticmethod
    def is_trailer(block_index: int) -> bool:
        return block_index % SECTOR_BLOCK_COUNT == 3

    @staticmethod
    def sector_of(block_index: int) -> int:
        return block_index // SECTOR_BLOCK_COUNT

    @staticmethod
    def trailer_block(sector: int) -> int:
        if not 0 <= sector < SECTOR_COUNT:
            raise IndexError(f"Sektor di luar jangkauan: {sector}")
        return sector * SECTOR_BLOCK_COUNT + 3

    # ------------------------------------------------------------------
    # UID dan blok manufaktur
    # ------------------------------------------------------------------
    @property
    def block0(self) -> bytes:
        return self.block(0)

    @property
    def uid(self) -> bytes:
        return self.block0[:4]

    @property
    def uid_hex(self) -> str:
        return self.uid.hex().upper()

    @property
    def bcc(self) -> int:
        return self.block0[4]

    @property
    def bcc_calculated(self) -> int:
        return self.uid[0] ^ self.uid[1] ^ self.uid[2] ^ self.uid[3]

    @property
    def bcc_ok(self) -> bool:
        return self.bcc == self.bcc_calculated

    @property
    def sak(self) -> int:
        return self.block0[5]

    @property
    def atqa(self) -> bytes:
        return self.block0[6:8]

    @property
    def atqa_hex(self) -> str:
        return self.atqa.hex().upper()

    @property
    def manufacturer(self) -> bytes:
        return self.block0[8:16]

    def set_uid(self, uid: bytes) -> None:
        if len(uid) != 4:
            raise CardError("UID harus 4 byte")
        self.data[0:4] = uid
        self.data[4] = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]

    # ------------------------------------------------------------------
    # Sector trailer
    # ------------------------------------------------------------------
    def key_a(self, block_index: int) -> bytes:
        if not self.is_trailer(block_index):
            raise CardError(f"Blok {block_index} bukan trailer")
        start = block_index * BLOCK_SIZE
        return bytes(self.data[start : start + 6])

    def access_bits(self, block_index: int) -> bytes:
        if not self.is_trailer(block_index):
            raise CardError(f"Blok {block_index} bukan trailer")
        start = block_index * BLOCK_SIZE
        return bytes(self.data[start + 6 : start + 9])

    def gpb(self, block_index: int) -> int:
        if not self.is_trailer(block_index):
            raise CardError(f"Blok {block_index} bukan trailer")
        return self.data[block_index * BLOCK_SIZE + 9]

    def key_b(self, block_index: int) -> bytes:
        if not self.is_trailer(block_index):
            raise CardError(f"Blok {block_index} bukan trailer")
        start = block_index * BLOCK_SIZE
        return bytes(self.data[start + 10 : start + 16])

    def trailer_is_default(self, block_index: int) -> bool:
        return (
            self.key_a(block_index) == DEFAULT_KEY
            and self.key_b(block_index) == DEFAULT_KEY
            and self.access_bits(block_index) == DEFAULT_ACCESS_BITS
            and self.gpb(block_index) == DEFAULT_GPB
        )

    # ------------------------------------------------------------------
    # Record: payload + tail
    # ------------------------------------------------------------------
    @staticmethod
    def record_data_blocks(base: int) -> list[int]:
        """22 blok data pada satu record, tanpa blok trailer."""
        if base < 0 or base + RECORD_BLOCK_COUNT > BLOCK_COUNT:
            raise IndexError(f"Awal record tidak valid: {base}")
        return [
            index
            for index in range(base, base + RECORD_BLOCK_COUNT)
            if not Card.is_trailer(index)
        ]

    @classmethod
    def record_payload_blocks(cls, base: int) -> list[int]:
        return cls.record_data_blocks(base)[:PAYLOAD_BLOCK_COUNT]

    @classmethod
    def record_tail_blocks(cls, base: int) -> list[int]:
        return cls.record_data_blocks(base)[PAYLOAD_BLOCK_COUNT:]

    def record_data(self, base: int) -> bytes:
        return b"".join(self.block(index) for index in self.record_data_blocks(base))

    def record_payload(self, base: int) -> bytes:
        return b"".join(
            self.block(index) for index in self.record_payload_blocks(base)
        )

    def tail(self, base: int) -> bytes:
        return b"".join(self.block(index) for index in self.record_tail_blocks(base))

    def tail_without_counter(self, base: int) -> bytes:
        value = bytearray(self.tail(base))
        value[TAIL_COUNTER_OFFSET : TAIL_COUNTER_OFFSET + COUNTER_SIZE] = b"\x00\x00"
        return bytes(value)

    def payloads(self) -> tuple[bytes, bytes]:
        return (
            self.record_payload(RECORD_STARTS[0]),
            self.record_payload(RECORD_STARTS[1]),
        )

    def tails(self) -> tuple[bytes, bytes]:
        return (self.tail(RECORD_STARTS[0]), self.tail(RECORD_STARTS[1]))

    @property
    def payload(self) -> bytes:
        """Payload record pertama (192 byte)."""
        return self.record_payload(RECORD_STARTS[0])

    @property
    def payload_hex(self) -> str:
        return self.payload.hex().upper()

    @property
    def payloads_equal(self) -> bool:
        first, second = self.payloads()
        return first == second

    @property
    def tails_equal_without_counter(self) -> bool:
        first, second = self.tails()
        a = bytearray(first)
        b = bytearray(second)
        a[TAIL_COUNTER_OFFSET : TAIL_COUNTER_OFFSET + COUNTER_SIZE] = b"\x00\x00"
        b[TAIL_COUNTER_OFFSET : TAIL_COUNTER_OFFSET + COUNTER_SIZE] = b"\x00\x00"
        return bytes(a) == bytes(b)

    # ------------------------------------------------------------------
    # Counter
    # ------------------------------------------------------------------
    def counter_at_block(self, block_index: int) -> int:
        start = block_index * BLOCK_SIZE + COUNTER_OFFSET
        return int.from_bytes(self.data[start : start + COUNTER_SIZE], "little")

    def set_counter_at_block(self, block_index: int, value: int) -> None:
        if not 0 <= value <= MAX_COUNTER:
            raise ValueError(f"Counter harus 0..{MAX_COUNTER}, bukan {value}")
        start = block_index * BLOCK_SIZE + COUNTER_OFFSET
        self.data[start : start + COUNTER_SIZE] = value.to_bytes(2, "little")

    @property
    def counters(self) -> tuple[int, int]:
        return tuple(self.counter_at_block(block) for block in COUNTER_BLOCKS)  # type: ignore[return-value]

    @property
    def counter(self) -> int:
        return self.counter_at_block(COUNTER_BLOCKS[0])

    @property
    def counter_hex(self) -> str:
        return f"{self.counter:04X}"

    @property
    def counter_synced(self) -> bool:
        return self.counters[0] == self.counters[1]

    def set_counter(self, value: int, both: bool = True) -> "Card":
        blocks = COUNTER_BLOCKS if both else (COUNTER_BLOCKS[0],)
        for block in blocks:
            self.set_counter_at_block(block, value)
        return self

    def counter_header(self, block_index: int) -> bytes:
        start = block_index * BLOCK_SIZE
        return bytes(self.data[start : start + COUNTER_HEADER_SIZE])

    @property
    def counter_headers(self) -> tuple[bytes, bytes]:
        return tuple(self.counter_header(block) for block in COUNTER_BLOCKS)  # type: ignore[return-value]

    @property
    def counter_fill(self) -> int | None:
        headers = self.counter_headers
        if headers[0] != headers[1]:
            return None
        first = headers[0][0]
        if all(byte == first for byte in headers[0]):
            return first
        return None

    @property
    def fill_byte(self) -> int | None:
        return self.counter_fill

    def set_counter_header(self, fill: int, both: bool = True) -> "Card":
        if not 0 <= fill <= 0xFF:
            raise ValueError("Fill harus 0..255")
        blocks = COUNTER_BLOCKS if both else (COUNTER_BLOCKS[0],)
        for block in blocks:
            start = block * BLOCK_SIZE
            self.data[start : start + COUNTER_HEADER_SIZE] = bytes([fill]) * COUNTER_HEADER_SIZE
        return self

    def set_tail_fill(self, fill: int, both: bool = True) -> "Card":
        """Samakan pola tail dengan chip penuh (FF) atau chip kosong (00).

        Hanya bagian tail yang memang berisi pola fill yang diubah; payload,
        counter, dan blok 30/32/60/62 tidak disentuh.
        """
        if not 0 <= fill <= 0xFF:
            raise ValueError("Fill harus 0..255")
        bases = RECORD_STARTS if both else (RECORD_STARTS[0],)
        for base in bases:
            for tail_index, block in enumerate(self.record_tail_blocks(base)):
                start = block * BLOCK_SIZE
                if tail_index == 0:
                    # Blok 20/49: dua byte pertama FE FE adalah bagian data.
                    self.data[start + 2 : start + BLOCK_SIZE] = bytes([fill]) * (
                        BLOCK_SIZE - 2
                    )
                elif tail_index in (1, 2, 3, 4, 5, 6):
                    self.data[start : start + BLOCK_SIZE] = bytes([fill]) * BLOCK_SIZE
                elif tail_index == TAIL_COUNTER_INDEX:
                    counter = bytes(
                        self.data[start + COUNTER_OFFSET : start + COUNTER_OFFSET + COUNTER_SIZE]
                    )
                    self.data[start : start + COUNTER_HEADER_SIZE] = (
                        bytes([fill]) * COUNTER_HEADER_SIZE
                    )
                    self.data[
                        start + COUNTER_OFFSET : start + COUNTER_OFFSET + COUNTER_SIZE
                    ] = counter
                    self.data[
                        start + COUNTER_OFFSET + COUNTER_SIZE : start + BLOCK_SIZE
                    ] = b"\x00" * (BLOCK_SIZE - COUNTER_OFFSET - COUNTER_SIZE)
                elif tail_index in (8, 9):
                    # Blok 30/32 dan 60/62 selalu nol pada format asli.
                    self.data[start : start + BLOCK_SIZE] = b"\x00" * BLOCK_SIZE
        return self

    # ------------------------------------------------------------------
    # Operasi record
    # ------------------------------------------------------------------
    def sync_records(self) -> "Card":
        """Salin 22 blok data record 1 ke record 2 (counter ikut tersalin)."""
        src_blocks = self.record_data_blocks(RECORD_STARTS[0])
        dst_blocks = self.record_data_blocks(RECORD_STARTS[1])
        for src, dst in zip(src_blocks, dst_blocks):
            self.set_block(dst, self.block(src))
        return self

    def normalize_tail_fill(self, fill: int) -> "Card":
        return self.set_tail_fill(fill, both=True)

    # ------------------------------------------------------------------
    # Validasi / perbandingan
    # ------------------------------------------------------------------
    def validation(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if len(self.data) != CARD_SIZE:
            issues.append(ValidationIssue("error", f"Ukuran data {len(self.data)} byte"))
            return issues

        if not self.bcc_ok:
            issues.append(
                ValidationIssue(
                    "error",
                    f"BCC tidak cocok: 0x{self.bcc:02X}, seharusnya 0x{self.bcc_calculated:02X}",
                )
            )

        c1, c2 = self.counters
        if c1 != c2:
            issues.append(
                ValidationIssue(
                    "warning",
                    f"Counter record 1 ({c1}) != record 2 ({c2})",
                )
            )
        for block, value in zip(COUNTER_BLOCKS, self.counters):
            if not 0 <= value <= MAX_COUNTER:
                issues.append(
                    ValidationIssue(
                        "error", f"Counter blok {block} di luar 0..{MAX_COUNTER}"
                    )
                )

        if not self.payloads_equal:
            issues.append(
                ValidationIssue(
                    "warning", "Payload record 1 dan record 2 berbeda"
                )
            )
        if not self.tails_equal_without_counter:
            issues.append(
                ValidationIssue(
                    "warning",
                    "Tail record 1 dan record 2 berbeda (selain counter)",
                )
            )

        bad_trailers = [
            block
            for block in range(BLOCK_COUNT)
            if self.is_trailer(block) and not self.trailer_is_default(block)
        ]
        if bad_trailers:
            issues.append(
                ValidationIssue(
                    "warning",
                    "Trailer dengan key/akses non-default: "
                    + ", ".join(str(block) for block in bad_trailers),
                )
            )

        if not issues:
            issues.append(ValidationIssue("info", "Struktur kartu valid"))
        return issues

    def validate(self) -> list[ValidationIssue]:
        return self.validation()

    def has_errors(self) -> bool:
        return any(issue.level == "error" for issue in self.validation())

    def diff_blocks(self, other: "Card") -> list[tuple[int, bytes, bytes]]:
        if len(self.data) != len(other.data):
            raise CardError("Ukuran kedua kartu berbeda")
        result: list[tuple[int, bytes, bytes]] = []
        for index in range(BLOCK_COUNT):
            a = self.block(index)
            b = other.block(index)
            if a != b:
                result.append((index, a, b))
        return result

    def diff_bytes(self, other: "Card") -> list[int]:
        if len(self.data) != len(other.data):
            raise CardError("Ukuran kedua kartu berbeda")
        return [
            index
            for index, (a, b) in enumerate(zip(self.data, other.data))
            if a != b
        ]

    # ------------------------------------------------------------------
    # Ringkasan
    # ------------------------------------------------------------------
    def summary(self) -> dict:
        issues = self.validation()
        return {
            "source": str(self.source) if self.source else None,
            "uid": self.uid_hex,
            "bcc": f"{self.bcc:02X}",
            "bcc_ok": self.bcc_ok,
            "sak": f"{self.sak:02X}",
            "atqa": self.atqa_hex,
            "manufacturer": self.manufacturer.hex().upper(),
            "counters": list(self.counters),
            "counter": self.counter,
            "counter_hex": self.counter_hex,
            "counter_synced": self.counter_synced,
            "counter_fill": (
                f"{self.counter_fill:02X}"
                if self.counter_fill is not None
                else None
            ),
            "payload_sha256": hashlib.sha256(self.payload).hexdigest(),
            "payloads_equal": self.payloads_equal,
            "tails_equal_without_counter": self.tails_equal_without_counter,
            "valid": not self.has_errors(),
            "issues": [
                {"level": issue.level, "message": issue.message} for issue in issues
            ],
        }

    def __repr__(self) -> str:
        return (
            f"Card(uid={self.uid_hex}, counter={self.counter}, "
            f"source={self.source!s})"
        )


def load_card(path: str | Path) -> Card:
    return Card.from_file(path)


def load_cards(paths: Iterable[str | Path]) -> list[Card]:
    return [load_card(path) for path in paths]
