from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .card import (
    KNOWN_COUNTERS,
    KNOWN_FULL_COUNTER,
    MAX_COUNTER,
    RECORD_STARTS,
    Card,
)


@dataclass
class CloneSpec:
    source: Card
    counter: int
    label: str
    description: str = ""
    fill: int | None = None
    normalize_records: bool = True
    tail_from: Card | None = None
    uid: bytes | None = None

    def file_stem(self) -> str:
        return f"{self.source.uid_hex}_{self.label}"


@dataclass
class CloneResult:
    spec: CloneSpec
    card: Card
    bin_path: Path
    json_path: Path
    scripts: dict[str, Path] = field(default_factory=dict)

    def manifest(self) -> dict:
        return {
            "label": self.spec.label,
            "description": self.spec.description,
            "source": str(self.spec.source.source) if self.spec.source.source else None,
            "source_uid": self.spec.source.uid_hex,
            "source_counter": self.spec.source.counter,
            "counter": self.spec.counter,
            "counter_hex": f"{self.spec.counter:04X}",
            "fill": f"{self.spec.fill:02X}" if self.spec.fill is not None else None,
            "uid": self.card.uid_hex,
            "uid_changed": self.card.uid_hex != self.spec.source.uid_hex,
            "file": self.bin_path.name,
            "sha256": hashlib.sha256(self.card.data).hexdigest(),
            "valid": not self.card.has_errors(),
            "scripts": {key: path.name for key, path in self.scripts.items()},
        }


def make_clone(spec: CloneSpec) -> Card:
    if not 0 <= spec.counter <= MAX_COUNTER:
        raise ValueError(f"Counter harus 0..{MAX_COUNTER}, bukan {spec.counter}")

    card = spec.source.copy()

    if spec.tail_from is not None:
        source_tail = spec.tail_from.record_tail_blocks(RECORD_STARTS[0])
        target_tail_1 = card.record_tail_blocks(RECORD_STARTS[0])
        target_tail_2 = card.record_tail_blocks(RECORD_STARTS[1])
        for src_block, dst1, dst2 in zip(source_tail, target_tail_1, target_tail_2):
            value = spec.tail_from.block(src_block)
            card.set_block(dst1, value)
            card.set_block(dst2, value)

    if spec.normalize_records:
        card.sync_records()

    if spec.fill is not None:
        card.set_tail_fill(spec.fill, both=True)

    card.set_counter(spec.counter, both=True)

    if spec.uid is not None:
        card.set_uid(spec.uid)

    return card


def _find_card(cards: Sequence[Card], uid: str) -> Card | None:
    for card in cards:
        if card.uid_hex.upper() == uid.upper():
            return card
    return None


def derive_uid(card: Card, salt: bytes = b"gtink-uid-v1") -> bytes:
    """UID 4 byte deterministik yang berbeda dari UID dump yang diketahui.

    UID ini dipakai untuk menguji apakah printer menyimpan riwayat UID/counter.
    BCC akan dihitung ulang oleh ``Card.set_uid``.
    """
    known = {bytes.fromhex(uid) for uid in KNOWN_COUNTERS}
    known.add(card.uid)
    digest = hashlib.sha256(card.payload + salt).digest()
    counter = 0
    while True:
        uid = digest[:4]
        if uid not in known and uid not in (b"\x00\x00\x00\x00", b"\xFF\xFF\xFF\xFF"):
            return uid
        counter += 1
        digest = hashlib.sha256(digest + counter.to_bytes(4, "little")).digest()


def recommended_specs(cards: Sequence[Card]) -> list[CloneSpec]:
    if not cards:
        return []

    full_cards = [card for card in cards if card.counter > 30000]
    low_cards = [card for card in cards if card.counter <= 30000]
    primary = _find_card(cards, "1EB75C2C") or (full_cards[0] if full_cards else cards[0])
    low = _find_card(cards, "BE8AAA9B") or (low_cards[0] if low_cards else None)

    specs: list[CloneSpec] = []

    # Kontrol: data harus sama persis dengan dump sumber.
    specs.append(
        CloneSpec(
            source=primary,
            counter=primary.counter,
            label=f"exact_{primary.counter}",
            description=(
                "Kontrol: clone persis dari dump sumber. "
                "Uji dulu apakah printer menerima kartu magic/UID hasil clone."
            ),
        )
    )
    specs.append(
        CloneSpec(
            source=primary,
            counter=KNOWN_FULL_COUNTER,
            label=f"full_{KNOWN_FULL_COUNTER}",
            description=(
                "Kandidat utama: counter nominal penuh 65000, fill dan payload "
                "dipertahankan dari chip penuh."
            ),
        )
    )
    specs.append(
        CloneSpec(
            source=primary,
            counter=MAX_COUNTER,
            label=f"max_{MAX_COUNTER}",
            description="Kandidat cadangan: counter maksimum 16-bit 65535.",
        )
    )

    new_uid = derive_uid(primary)
    specs.append(
        CloneSpec(
            source=primary,
            counter=KNOWN_FULL_COUNTER,
            label=f"full_{KNOWN_FULL_COUNTER}_newuid_{new_uid.hex().upper()}",
            description=(
                "UID baru yang diturunkan dari payload, counter 65000. "
                "Untuk menguji apakah printer menolak UID yang sudah dikenal "
                "atau mendeteksi rollback counter."
            ),
            uid=new_uid,
        )
    )

    # Semua sumber chip penuh lain, masing-masing exact dan counter 65000.
    for card in full_cards:
        if card.uid == primary.uid:
            continue
        specs.append(
            CloneSpec(
                source=card,
                counter=card.counter,
                label=f"exact_{card.counter}",
                description=(
                    f"Kontrol sumber {card.uid_hex}: clone persis, "
                    "payload dan counter asli dipertahankan."
                ),
            )
        )
        specs.append(
            CloneSpec(
                source=card,
                counter=KNOWN_FULL_COUNTER,
                label=f"full_{KNOWN_FULL_COUNTER}",
                description=(
                    f"Kandidat sumber {card.uid_hex}: counter 65000, "
                    "payload sumber dipertahankan."
                ),
            )
        )

    if low is not None:
        specs.append(
            CloneSpec(
                source=low,
                counter=low.counter,
                label=f"exact_{low.counter}",
                description="Kontrol chip low-ink: counter dan fill 00 dipertahankan.",
            )
        )
        specs.append(
            CloneSpec(
                source=low,
                counter=KNOWN_FULL_COUNTER,
                label=f"full_{KNOWN_FULL_COUNTER}_keep00",
                description=(
                    "Chip low-ink dinaikkan ke 65000 dengan fill 00 asli. "
                    "Payload low-ink dipertahankan."
                ),
            )
        )
        specs.append(
            CloneSpec(
                source=low,
                counter=KNOWN_FULL_COUNTER,
                label=f"full_{KNOWN_FULL_COUNTER}_fillFF",
                description=(
                    "Chip low-ink dinaikkan ke 65000 dan tail dinormalisasi ke "
                    "format chip penuh (FF)."
                ),
                fill=0xFF,
            )
        )

    return specs


def _safe_name(text: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in text
    )


def write_clone_result(
    spec: CloneSpec,
    out_dir: str | Path,
    script_backends: Iterable[str] = ("gen1a", "gen2", "gen4"),
) -> CloneResult:
    from .proxmark import generate_scripts

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    card = make_clone(spec)
    stem = _safe_name(spec.file_stem())
    bin_path = output / f"{stem}.bin"
    json_path = output / f"{stem}.json"
    card.save(bin_path)
    card.save_json(json_path)

    scripts: dict[str, Path] = {}
    script_dir = output / "scripts"
    for backend in script_backends:
        scripts[backend] = generate_scripts(
            bin_path,
            script_dir,
            backend=backend,
            stem=stem,
            card=card,
        )

    return CloneResult(
        spec=spec,
        card=card,
        bin_path=bin_path,
        json_path=json_path,
        scripts=scripts,
    )


def write_recommended(
    cards: Sequence[Card],
    out_dir: str | Path,
    script_backends: Iterable[str] = ("gen1a", "gen2", "gen4"),
) -> list[CloneResult]:
    specs = recommended_specs(cards)
    results = [
        write_clone_result(spec, out_dir, script_backends=script_backends)
        for spec in specs
    ]
    _write_manifest(results, out_dir)
    _write_test_readme(results, out_dir)
    return results


def _write_manifest(results: Sequence[CloneResult], out_dir: str | Path) -> Path:
    output = Path(out_dir)
    manifest = {
        "tool": "gtink",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clones": [result.manifest() for result in results],
    }
    path = output / "manifest.json"
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _write_test_readme(results: Sequence[CloneResult], out_dir: str | Path) -> Path:
    output = Path(out_dir)
    lines = [
        "PAKET UJI CLONE CHIP EAJet / GT1000",
        "=" * 48,
        "",
        "Urutan pengujian yang disarankan:",
        "1. Tulis file exact (kontrol) lebih dulu, lalu pasang ke printer.",
        "2. Catat pesan printer. Jika exact diterima, lanjut ke counter 65000.",
        "3. Jika 65000 ditolak, coba max_65535.",
        "4. Jika printer menolak UID sumber, coba file newuid (UID baru).",
        "5. Coba juga sumber lain (5EEFAB9B / FE7EA17E) dengan counter 65000.",
        "6. Untuk chip low-ink, coba keep00 lalu fillFF.",
        "",
        "Daftar file:",
    ]
    for result in results:
        fill = (
            f"{result.spec.fill:02X}"
            if result.spec.fill is not None
            else "asli"
        )
        lines.append(
            f"- {result.bin_path.name}: UID {result.card.uid_hex}, "
            f"counter {result.spec.counter} (0x{result.spec.counter:04X}), "
            f"fill={fill}"
        )
        lines.append(f"  {result.spec.description}")
    lines.extend(
        [
            "",
            "Perintah tulis Gen1a (magic card):",
            "  py gtink.py write --file <file.bin> --backend gen1a --port COM11 --yes",
            "",
            "Script Proxmark3 ada di folder scripts/.",
            "Peringatan: hanya gunakan pada kartu/printer milik sendiri. "
            "Menulis blok 0 dapat mengubah UID dan membuat kartu tidak terbaca "
            "jika data blok 0 salah. Cadangkan dump asli sebelum menulis.",
            "",
            "Jika printer menolak semua file dengan 'Chip invalid' atau "
            "'Chip mismatch', counter bukan penyebabnya; kemungkinan ada "
            "signature/UID binding atau kartu magic terdeteksi.",
        ]
    )
    path = output / "README_UJI.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def format_results(results: Sequence[CloneResult]) -> str:
    if not results:
        return "Tidak ada clone yang dibuat."
    headers = ["File", "UID", "Counter", "Fill", "Valid"]
    rows = []
    for result in results:
        rows.append(
            [
                result.bin_path.name,
                result.card.uid_hex,
                f"{result.spec.counter} (0x{result.spec.counter:04X})",
                f"{result.spec.fill:02X}" if result.spec.fill is not None else "asli",
                "ya" if not result.card.has_errors() else "TIDAK",
            ]
        )
    widths = [
        max(len(headers[i]), max((len(row[i]) for row in rows), default=0))
        for i in range(len(headers))
    ]
    out = ["  ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))]
    out.append("  ".join("-" * width for width in widths))
    for row in rows:
        out.append("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(out)
