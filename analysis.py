from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

from .card import (
    COUNTER_BLOCKS,
    COUNTER_OFFSET,
    KNOWN_FULL_COUNTER,
    MAX_COUNTER,
    PAYLOAD_SIZE,
    RECORD_STARTS,
    TAIL_SIZE,
    Card,
    load_cards,
)
from .paths import resolve_existing


DEFAULT_DUMP_DIR = Path("tij gt1000 CHIP INK")
DUMP_GLOB = "hf-mf-*-dump.bin"


def discover_dumps(root: str | Path = DEFAULT_DUMP_DIR) -> list[Path]:
    directory = resolve_existing(root)
    if not directory.exists():
        return []
    return sorted(directory.glob(DUMP_GLOB))


def load_dump_dir(root: str | Path = DEFAULT_DUMP_DIR) -> list[Card]:
    paths = discover_dumps(root)
    if not paths:
        raise FileNotFoundError(
            f"Tidak ada dump '{DUMP_GLOB}' di folder: {resolve_existing(root).resolve()}"
        )
    return load_cards(paths)


def _yn(value: bool) -> str:
    return "ya" if value else "tidak"


def format_info(card: Card, title: str | None = None) -> str:
    lines: list[str] = []
    if title:
        lines.append(title)
    source = str(card.source) if card.source else "(tidak ada)"
    lines.extend(
        [
            f"UID              : {card.uid_hex}",
            f"BCC              : {card.bcc:02X} "
            f"({'OK' if card.bcc_ok else 'SALAH, harus ' + format(card.bcc_calculated, '02X')})",
            f"SAK / ATQA       : {card.sak:02X} / {card.atqa_hex}",
            f"Manufacturer     : {card.manufacturer.hex().upper()}",
            f"Counter R1 / R2  : {card.counters[0]} / {card.counters[1]} "
            f"(0x{card.counters[0]:04X} / 0x{card.counters[1]:04X})",
            f"Counter sinkron  : {_yn(card.counter_synced)}",
            f"Fill tail        : {card.counter_fill:02X}"
            if card.counter_fill is not None
            else "Fill tail        : tidak seragam",
            f"Payload R1/R2    : {_yn(card.payloads_equal)}",
            f"Tail R1/R2       : {_yn(card.tails_equal_without_counter)}",
            f"Payload SHA-256  : {hashlib.sha256(card.payload).hexdigest()}",
            f"Sumber           : {source}",
        ]
    )
    lines.append("Validasi         :")
    for issue in card.validation():
        lines.append(f"  - {issue}")
    return "\n".join(lines)


def format_table(cards: Sequence[Card]) -> str:
    headers = [
        "UID",
        "Counter R1",
        "Counter R2",
        "Hex",
        "Fill",
        "Payload",
        "Tail",
        "Sumber",
    ]
    rows: list[list[str]] = []
    for card in cards:
        rows.append(
            [
                card.uid_hex,
                str(card.counters[0]),
                str(card.counters[1]),
                f"0x{card.counter:04X}",
                f"{card.counter_fill:02X}"
                if card.counter_fill is not None
                else "?",
                _yn(card.payloads_equal),
                _yn(card.tails_equal_without_counter),
                card.source.name if card.source else "-",
            ]
        )
    widths = [
        max(len(headers[i]), max((len(row[i]) for row in rows), default=0))
        for i in range(len(headers))
    ]
    sep = "  "
    out = [sep.join(h.ljust(widths[i]) for i, h in enumerate(headers))]
    out.append(sep.join("-" * w for w in widths))
    for row in rows:
        out.append(sep.join(row[i].ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(out)


def candidate_counters(cards: Sequence[Card]) -> list[tuple[int, str, str]]:
    """Nilai counter yang layak diuji, dari yang paling disarankan."""
    values: list[tuple[int, str, str]] = []
    seen: set[int] = set()

    def add(value: int, label: str, reason: str) -> None:
        if value not in seen:
            seen.add(value)
            values.append((value, label, reason))

    add(
        KNOWN_FULL_COUNTER,
        "full-65000",
        "Nilai nominal penuh yang paling masuk akal; dekat dengan 64016/64606/64516",
    )
    add(MAX_COUNTER, "max-65535", "Batas maksimum 16-bit; cadangan jika 65000 ditolak")
    for value in sorted({card.counter for card in cards}, reverse=True):
        add(value, f"asli-{value}", "Nilai asli dari dump; berguna sebagai kontrol")
    add(64606, "full-64606", "Counter penuh dari dump 5EEFAB9B")
    add(64516, "full-64516", "Counter penuh dari dump FE7EA17E")
    add(64016, "full-64016", "Counter penuh dari dump 1EB75C2C")
    low_values = [card.counter for card in cards if card.counter < 30000]
    for value in low_values:
        add(value, f"low-{value}", "Counter rendah dari chip tinta hampir habis")
    return values


def _payload_diff_positions(cards: Sequence[Card]) -> list[int]:
    payloads = [card.payload for card in cards]
    if not payloads:
        return []
    return [
        index
        for index in range(PAYLOAD_SIZE)
        if len({payload[index] for payload in payloads}) > 1
    ]


def _tail_diff_positions(cards: Sequence[Card]) -> list[int]:
    tails = [card.tail(RECORD_STARTS[0]) for card in cards]
    if not tails:
        return []
    return [
        index
        for index in range(TAIL_SIZE)
        if len({tail[index] for tail in tails}) > 1
    ]


def analyze(cards: Sequence[Card]) -> str:
    if not cards:
        return "Tidak ada kartu untuk dianalisis."

    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("ANALISIS DUMP CHIP KARTRID EAJet / GT1000")
    lines.append("=" * 78)
    lines.append("")
    lines.append(format_table(cards))
    lines.append("")

    common_manufacturer = {
        card.manufacturer for card in cards
    }
    lines.append(
        "Manufacturer block (byte 8-15) sama untuk semua dump: "
        + _yn(len(common_manufacturer) == 1)
    )
    if len(common_manufacturer) == 1:
        lines.append(f"  Nilai: {next(iter(common_manufacturer)).hex().upper()}")
    lines.append("")

    lines.append("Layout record:")
    lines.append(
        f"  Record 1: blok {RECORD_STARTS[0]}..{RECORD_STARTS[0] + 28}, "
        f"Record 2: blok {RECORD_STARTS[1]}..{RECORD_STARTS[1] + 28}"
    )
    lines.append(
        "  Tiap record: 29 blok fisik, 7 blok trailer, 22 blok data = 352 byte"
    )
    lines.append(
        f"  12 blok pertama = payload {PAYLOAD_SIZE} byte; "
        f"10 blok berikutnya = tail {TAIL_SIZE} byte"
    )
    lines.append(
        f"  Counter: blok {COUNTER_BLOCKS[0]} dan {COUNTER_BLOCKS[1]}, "
        f"offset {COUNTER_OFFSET}, 16-bit little-endian"
    )
    lines.append("")

    lines.append("Counter yang ditemukan:")
    for card in cards:
        lines.append(
            f"  {card.uid_hex}: {card.counters[0]} / {card.counters[1]} "
            f"(0x{card.counters[0]:04X} / 0x{card.counters[1]:04X}), "
            f"fill={card.counter_fill:02X}"
            if card.counter_fill is not None
            else f"  {card.uid_hex}: {card.counters[0]} / {card.counters[1]}"
        )
    lines.append("")
    lines.append(
        "Interpretasi: counter adalah sisa tinta. Nilai 64016-64606 pada chip "
        "penuh, 12107 pada chip low-ink."
    )
    lines.append(
        "  LOW_INK_THRESHOLD=15 dan LOW_INK_THRESHOLD_UPVALUE=60 pada SysParam.ini; "
        "12107/65000 sekitar 18.6%."
    )
    lines.append(
        f"  Nominal penuh yang paling mungkin: {KNOWN_FULL_COUNTER} (0x{KNOWN_FULL_COUNTER:04X}); "
        f"batas maksimum {MAX_COUNTER} (0x{MAX_COUNTER:04X})."
    )
    lines.append("")

    full_cards = [card for card in cards if card.counter > 30000]
    low_cards = [card for card in cards if card.counter <= 30000]
    if full_cards:
        lines.append("Ciri chip penuh:")
        lines.append(
            "  - Counter tinggi (64016-64606)"
        )
        lines.append(
            "  - Tail diisi 0xFF, termasuk 10 byte header blok counter"
        )
        lines.append("")
    if low_cards:
        lines.append("Ciri chip low-ink:")
        for card in low_cards:
            lines.append(
                f"  - {card.uid_hex}: counter {card.counter}, fill={card.counter_fill:02X}, "
                "payload tetap sama"
            )
        lines.append(
            "  - Isi tail yang tidak terpakai 0x00, bukan 0xFF; bisa jadi format "
            "programmer yang berbeda."
        )
        lines.append("")

    payload_positions = _payload_diff_positions(cards)
    tail_positions = _tail_diff_positions(cards)
    full_tail_positions = _tail_diff_positions(full_cards) if len(full_cards) > 1 else []
    lines.append(f"Posisi payload yang berbeda antar dump: {len(payload_positions)} byte")
    if payload_positions:
        lines.append("  " + ", ".join(str(i) for i in payload_positions))
    lines.append(f"Posisi tail yang berbeda antar dump: {len(tail_positions)} byte")
    if tail_positions:
        lines.append("  " + ", ".join(str(i) for i in tail_positions))
    if full_tail_positions:
        lines.append(
            "  Pada sesama chip penuh, tail hanya berbeda di offset: "
            + ", ".join(str(i) for i in full_tail_positions)
        )
    lines.append(
        "  Catatan: selain counter, chip low-ink juga berbeda pada pola fill 00 vs FF. "
        "Tidak ditemukan checksum atau signature yang menghubungkan counter ke payload."
    )
    lines.append("")

    lines.append("Kandidat counter untuk diuji (urut prioritas):")
    for value, label, reason in candidate_counters(cards):
        lines.append(f"  {value:5d}  0x{value:04X}  {label:<12} {reason}")
    lines.append("")
    lines.append("Strategi uji yang disarankan:")
    lines.append(
        "  1. Tulis clone EXACT dari satu dump penuh (counter sama) ke magic card."
    )
    lines.append(
        "     Ini menguji apakah printer menerima kartu magic/UID hasil clone."
    )
    lines.append(
        "  2. Jika exact diterima, tulis clone dengan counter 65000."
    )
    lines.append(
        "  3. Jika 65000 ditolak, coba 65535, lalu 64606/64516/64016."
    )
    lines.append(
        "  4. Untuk chip low-ink BE8AAA9B, coba pertahankan fill 00 dan juga "
        "varian yang dinormalisasi ke FF."
    )
    lines.append(
        "  5. Jika semua ditolak dengan pesan 'Chip invalid'/'Chip mismatch', "
        "masalahnya bukan counter; kemungkinan signature/UID atau kartu magic "
        "terdeteksi."
    )
    lines.append("")
    lines.append(
        "Kesimpulan: counter dapat diubah secara langsung, tetapi belum bisa "
        "dipastikan diterima printer tanpa pengujian fisik."
    )
    return "\n".join(lines)


def analyze_dump_dir(root: str | Path = DEFAULT_DUMP_DIR) -> str:
    return analyze(load_dump_dir(root))
