from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Callable

from .analysis import DEFAULT_DUMP_DIR, analyze, discover_dumps, format_table
from .card import KNOWN_COUNTERS, KNOWN_FULL_COUNTER, MAX_COUNTER, Card, load_cards
from .clone import CloneSpec, make_clone, write_recommended
from .proxmark import generate_scripts


Check = tuple[bool, str, str]


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_selftest(
    dump_dir: str | Path = DEFAULT_DUMP_DIR,
    verbose: bool = True,
) -> tuple[bool, list[Check]]:
    """Uji offline seluruh logika kartu, clone, dan pembuatan script.

    Tidak membutuhkan Proxmark3 atau printer.
    """
    checks: list[Check] = []

    def record(name: str, func: Callable[[], str | None]) -> None:
        try:
            detail = func() or ""
        except Exception as exc:  # sengaja menangkap semua agar laporan lengkap
            checks.append((False, name, f"{type(exc).__name__}: {exc}"))
            if verbose:
                print(f"[GAGAL] {name}: {type(exc).__name__}: {exc}")
        else:
            checks.append((True, name, detail))
            if verbose:
                print(f"[OK]    {name}" + (f" - {detail}" if detail else ""))

    paths = discover_dumps(dump_dir)

    def check_dumps() -> str:
        _expect(len(paths) >= 4, f"hanya {len(paths)} file dump ditemukan")
        return f"{len(paths)} file di {Path(dump_dir)}"

    record("Dump ditemukan", check_dumps)
    if not paths:
        return False, checks

    try:
        cards = load_cards(paths)
    except Exception as exc:
        checks.append((False, "Muat semua dump", f"{type(exc).__name__}: {exc}"))
        if verbose:
            print(f"[GAGAL] Muat semua dump: {exc}")
        return False, checks
    record("Muat semua dump", lambda: f"{len(cards)} kartu")

    primary = next((card for card in cards if card.uid_hex == "1EB75C2C"), cards[0])

    def check_known() -> str:
        for card in cards:
            expected = KNOWN_COUNTERS.get(card.uid_hex)
            _expect(expected is not None, f"UID {card.uid_hex} tidak dikenal")
            _expect(
                card.counter == expected,
                f"{card.uid_hex}: counter {card.counter}, seharusnya {expected}",
            )
        return f"{len(cards)} UID/counter cocok"

    record("UID dan counter dump", check_known)

    def check_structure() -> str:
        for card in cards:
            _expect(card.bcc_ok, f"{card.uid_hex}: BCC salah")
            _expect(card.payloads_equal, f"{card.uid_hex}: payload R1 != R2")
            _expect(
                card.tails_equal_without_counter,
                f"{card.uid_hex}: tail R1 != R2",
            )
            _expect(not card.has_errors(), f"{card.uid_hex}: validasi error")
        return "BCC, payload, tail, dan validasi OK"

    record("Struktur record", check_structure)

    def check_exact() -> str:
        for card in cards:
            clone = make_clone(CloneSpec(card, card.counter, "exact"))
            _expect(
                bytes(clone.data) == bytes(card.data),
                f"{card.uid_hex}: exact clone tidak identik",
            )
        return "semua exact clone identik"

    record("Exact clone", check_exact)

    def check_counter() -> str:
        clone = make_clone(CloneSpec(primary, KNOWN_FULL_COUNTER, "counter"))
        diff = set(clone.diff_bytes(primary))
        expected = {
            29 * 16 + 10,
            29 * 16 + 11,
            58 * 16 + 10,
            58 * 16 + 11,
        }
        _expect(diff == expected, f"byte berubah: {sorted(diff)}")
        _expect(clone.counters == (KNOWN_FULL_COUNTER, KNOWN_FULL_COUNTER), "counter")
        return "hanya 4 byte counter yang berubah"

    record("Edit counter 65000", check_counter)

    def check_uid() -> str:
        new_uid = bytes.fromhex("A1B2C3D4")
        clone = make_clone(CloneSpec(primary, primary.counter, "uid", uid=new_uid))
        _expect(clone.uid == new_uid, "UID tidak berubah")
        _expect(clone.bcc_ok, "BCC tidak dihitung ulang")
        diff = set(clone.diff_bytes(primary))
        _expect(diff == set(range(5)), f"byte berubah: {sorted(diff)}")
        return "UID dan BCC berubah, blok lain tetap"

    record("Ganti UID", check_uid)

    def check_low_fill() -> str:
        low = next((card for card in cards if card.counter <= 30000), None)
        _expect(low is not None, "tidak ada chip low-ink")
        clone = make_clone(
            CloneSpec(low, KNOWN_FULL_COUNTER, "lowfill", fill=0xFF)
        )
        _expect(clone.payload == low.payload, "payload berubah")
        _expect(clone.counters == (KNOWN_FULL_COUNTER, KNOWN_FULL_COUNTER), "counter")
        _expect(all(byte == 0xFF for byte in clone.counter_header(29)), "header 29")
        _expect(all(byte == 0xFF for byte in clone.counter_header(58)), "header 58")
        for block in (30, 32, 60, 62):
            _expect(clone.block(block) == b"\x00" * 16, f"blok {block} bukan nol")
        _expect(not clone.has_errors(), "validasi error")
        return "payload tetap, fill tail menjadi FF"

    record("Normalisasi chip low-ink", check_low_fill)

    def check_roundtrip() -> str:
        with tempfile.TemporaryDirectory(prefix="gtink_selftest_") as tmp:
            folder = Path(tmp)
            primary.save(folder / "card.bin")
            primary.save_json(folder / "card.json")
            loaded = Card.from_file(folder / "card.json")
            _expect(bytes(loaded.data) == bytes(primary.data), "JSON tidak identik")
            eml = folder / "card.eml"
            eml.write_text(
                "\n".join(primary.block(i).hex().upper() for i in range(64)) + "\n",
                encoding="utf-8",
            )
            loaded = Card.from_file(eml)
            _expect(bytes(loaded.data) == bytes(primary.data), "EML tidak identik")
        return "JSON dan EML bolak-balik identik"

    record("Format JSON/EML", check_roundtrip)

    def check_package() -> str:
        with tempfile.TemporaryDirectory(prefix="gtink_selftest_") as tmp:
            folder = Path(tmp)
            results = write_recommended(
                cards, folder, script_backends=("gen1a", "gen2", "gen4")
            )
            _expect(len(results) >= 9, f"hanya {len(results)} clone")
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            _expect(len(manifest["clones"]) == len(results), "manifest tidak cocok")
            _expect((folder / "README_UJI.txt").exists(), "README_UJI.txt hilang")
            for result in results:
                _expect(result.bin_path.exists(), f"{result.bin_path.name} hilang")
                _expect(result.json_path.exists(), f"{result.json_path.name} hilang")
                for backend in ("gen1a", "gen2", "gen4"):
                    _expect(
                        backend in result.scripts and result.scripts[backend].exists(),
                        f"script {backend} hilang untuk {result.bin_path.name}",
                    )
                loaded = Card.from_file(result.bin_path)
                _expect(not loaded.has_errors(), f"{loaded.uid_hex}: validasi error")
                _expect(
                    loaded.counters
                    == (result.spec.counter, result.spec.counter),
                    f"{loaded.uid_hex}: counter tidak cocok",
                )
            exact = next(
                result
                for result in results
                if result.spec.source.uid == primary.uid
                and result.spec.counter == primary.counter
                and result.spec.uid is None
                and result.spec.fill is None
            )
            _expect(
                bytes(exact.card.data) == bytes(primary.data),
                "exact clone dalam paket tidak identik",
            )
        return f"{len(results)} clone + manifest + README"

    record("Paket rekomendasi", check_package)

    def check_scripts() -> str:
        with tempfile.TemporaryDirectory(prefix="gtink_selftest_") as tmp:
            folder = Path(tmp)
            bin_path = folder / "sample.bin"
            primary.save(bin_path)
            gen1a = generate_scripts(bin_path, folder, "gen1a", "sample", primary)
            gen2 = generate_scripts(bin_path, folder, "gen2", "sample", primary)
            gen4 = generate_scripts(bin_path, folder, "gen4", "sample", primary)

            def commands(path: Path) -> list[str]:
                return [
                    line.strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]

            g1 = commands(gen1a)
            _expect(len(g1) == 1 and g1[0].startswith("hf mf cload"), "gen1a")
            _expect("--1k" in g1[0], "gen1a --1k")
            g2 = commands(gen2)
            _expect(len(g2) == 64, f"gen2 {len(g2)} baris")
            _expect(g2[0].startswith("hf mf wrbl --blk 1"), "gen2 blok 1")
            _expect(g2[-1].startswith("hf mf wrbl --blk 0"), "gen2 blok 0 terakhir")
            _expect("--force" in g2[-1], "gen2 --force blok 0")
            _expect(
                sum(1 for line in g2 if "--blk 0 " in line) == 1,
                "gen2 blok 0 ganda",
            )
            g4 = commands(gen4)
            _expect(len(g4) == 1 and g4[0].startswith("hf mf gload"), "gen4")
            _expect("--1k" in g4[0], "gen4 --1k")
        return "gen1a, gen2 (64 blok), gen4 valid"

    record("Script Proxmark3", check_scripts)

    def check_report() -> str:
        table = format_table(cards)
        for card in cards:
            _expect(card.uid_hex in table, f"{card.uid_hex} tidak ada di tabel")
        report = analyze(cards)
        _expect("Kandidat counter" in report, "bagian kandidat hilang")
        _expect(str(KNOWN_FULL_COUNTER) in report, "65000 tidak ada")
        _expect(str(MAX_COUNTER) in report, "65535 tidak ada")
        return "tabel dan laporan analisis lengkap"

    record("Laporan analisis", check_report)

    ok = all(item[0] for item in checks)
    if verbose:
        print("")
        print(
            ("SELFTEST LULUS" if ok else "SELFTEST GAGAL")
            + f" ({sum(1 for item in checks if item[0])}/{len(checks)})"
        )
    return ok, checks
