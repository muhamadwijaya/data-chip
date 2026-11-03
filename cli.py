from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from . import __version__
from .analysis import (
    DEFAULT_DUMP_DIR,
    analyze,
    format_info,
    format_table,
    load_dump_dir,
)
from .card import Card, CardError, load_card
from .clone import (
    CloneSpec,
    derive_uid,
    format_results,
    write_clone_result,
    write_recommended,
)
from .paths import resolve_existing
from .proxmark import (
    ProxmarkClient,
    ProxmarkError,
    find_port,
    generate_scripts,
    list_serial_ports,
)
from .replay import SETS as REPLAY_SETS
from .replay import format_table as format_replay_table
from .replay import get_set as get_replay_set
from .selftest import run_selftest


def _parse_int(value: str) -> int:
    text = value.strip()
    try:
        if text.lower().startswith("0x"):
            return int(text, 16)
        return int(text, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"angka tidak valid: {value}") from exc


def _parse_uid(value: str) -> bytes:
    text = re.sub(r"[\s:_-]", "", value)
    if len(text) != 8:
        raise argparse.ArgumentTypeError("UID harus 8 digit hex (4 byte)")
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"UID bukan hex yang valid: {value}") from exc


def _backends(args: argparse.Namespace) -> tuple[str, ...]:
    return tuple(dict.fromkeys(args.backend or ("gen1a", "gen2", "gen4")))


def _load_sources(args: argparse.Namespace) -> list[Card]:
    if args.source and args.source_uid:
        raise CardError("Pilih --source atau --source-uid, bukan keduanya")
    if args.source:
        return [load_card(resolve_existing(args.source))]
    cards = load_dump_dir(args.dir)
    if args.source_uid:
        target = args.source_uid.upper()
        for card in cards:
            if card.uid_hex == target:
                return [card]
        raise CardError(
            f"UID {target} tidak ditemukan di {args.dir}. "
            "Pilihan: " + ", ".join(card.uid_hex for card in cards)
        )
    return cards


def _client_kwargs(args: argparse.Namespace) -> dict:
    return {
        "client": args.client,
        "port": args.port,
        "timeout": args.timeout,
    }


def cmd_info(args: argparse.Namespace) -> int:
    if args.paths:
        cards = [load_card(resolve_existing(path)) for path in args.paths]
    else:
        cards = load_dump_dir(args.dir)

    if args.json:
        print(
            json.dumps(
                [card.summary() for card in cards],
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(format_table(cards))
    if args.detail:
        for card in cards:
            print()
            print(format_info(card, title=str(card.source or card.uid_hex)))
    else:
        print()
        print("Gunakan --detail untuk rincian tiap dump.")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    cards = load_dump_dir(args.dir)
    report = analyze(cards)
    print(report)
    if args.output:
        path = Path(args.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report + "\n", encoding="utf-8")
        print()
        print(f"Laporan disimpan: {path}")
    return 0


def cmd_clone(args: argparse.Namespace) -> int:
    backends = _backends(args)
    out_dir = Path(args.out).expanduser()

    if args.recommended:
        cards = load_dump_dir(args.dir)
        results = write_recommended(cards, out_dir, script_backends=backends)
        print(format_results(results))
        print()
        print(f"Folder output : {out_dir.resolve()}")
        print(f"Manifest      : {(out_dir / 'manifest.json').resolve()}")
        print(f"Panduan uji   : {(out_dir / 'README_UJI.txt').resolve()}")
        return 0

    cards = _load_sources(args)
    source = cards[0]
    if args.counter is None:
        raise CardError("--counter wajib untuk clone tunggal (atau pakai --recommended)")

    fill: int | None = {"keep": None, "00": 0x00, "ff": 0xFF}[args.fill]
    if args.fill_byte is not None:
        if not 0 <= args.fill_byte <= 0xFF:
            raise CardError("--fill-byte harus 0..255")
        fill = args.fill_byte

    new_uid = args.new_uid
    if args.random_uid:
        if new_uid is not None:
            raise CardError("Pilih --new-uid atau --random-uid, bukan keduanya")
        new_uid = derive_uid(source)

    label = args.label or f"custom_{args.counter}"
    if fill is not None:
        label += f"_fill{fill:02X}"
    if new_uid is not None:
        label += f"_uid{new_uid.hex().upper()}"

    tail_from = (
        load_card(resolve_existing(args.tail_from)) if args.tail_from else None
    )
    spec = CloneSpec(
        source=source,
        counter=args.counter,
        label=label,
        description="Clone custom dari CLI.",
        fill=fill,
        normalize_records=not args.no_sync,
        tail_from=tail_from,
        uid=new_uid,
    )
    result = write_clone_result(spec, out_dir, script_backends=backends)
    print(format_results([result]))
    print()
    print(f"BIN     : {result.bin_path.resolve()}")
    print(f"JSON    : {result.json_path.resolve()}")
    for backend, path in result.scripts.items():
        print(f"Script  : {backend:<5} {path.resolve()}")
    return 0


def cmd_scripts(args: argparse.Namespace) -> int:
    source = resolve_existing(args.file)
    if not source.is_file():
        raise CardError(f"File clone tidak ditemukan: {source}")
    stem = args.stem or source.stem
    for backend in _backends(args):
        path = generate_scripts(source, Path(args.out), backend, stem)
        print(path.resolve())
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    out = Path(args.out).expanduser()
    if out.suffix.lower() not in {".bin", ".json", ".eml"}:
        out = out.with_suffix(".bin")
    keys = resolve_existing(args.keys) if args.keys else None

    with ProxmarkClient(**_client_kwargs(args)) as client:
        info = client.search()
        print(
            f"Kartu terdeteksi: UID {info.uid_hex}"
            + (f", SAK {info.sak}" if info.sak else "")
            + (f", ATQA {info.atqa}" if info.atqa else "")
            + (f", magic: {info.magic}" if info.magic else "")
        )
        card, output = client.read_card(keys=keys, timeout=args.timeout)
        tail = "\n".join(output.splitlines()[-12:])
        if tail:
            print(tail)

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".json":
        card.save_json(out)
        print(f"JSON disimpan: {out.resolve()}")
    elif out.suffix.lower() == ".eml":
        card.save_eml(out)
        print(f"EML disimpan : {out.resolve()}")
    else:
        card.save(out)
        card.save_json(out.with_suffix(".json"))
        print(f"BIN disimpan : {out.resolve()}")
        print(f"JSON disimpan: {out.with_suffix('.json').resolve()}")
    print()
    print(format_info(card, title="Hasil baca kartu"))
    return 0


def _magic_warning(backend: str, magic: str | None) -> str | None:
    if not magic:
        return "Kemampuan magic tidak terdeteksi; pastikan kartu benar-benar magic."
    text = magic.lower()
    if backend == "gen1a" and "1a" not in text and "gen 1" not in text:
        return f"Backend gen1a dipilih, tetapi kartu terdeteksi: {magic}"
    if backend == "gen4" and "4" not in text:
        return f"Backend gen4 dipilih, tetapi kartu terdeteksi: {magic}"
    if backend == "gen2" and "2" not in text and "cuid" not in text:
        return f"Backend gen2 dipilih, tetapi kartu terdeteksi: {magic}"
    return None


def cmd_write(args: argparse.Namespace) -> int:
    source = resolve_existing(args.file)
    if not source.is_file():
        raise CardError(f"File clone tidak ditemukan: {source}")
    card = load_card(source)
    print(format_info(card, title="Clone yang akan ditulis"))
    print()
    if card.has_errors() and not args.allow_invalid:
        raise CardError(
            "Clone memiliki error validasi. Perbaiki dulu atau pakai --allow-invalid."
        )

    print("PERINGATAN:")
    print("  - Menulis ke kartu akan menimpa seluruh isi, termasuk blok 0/UID.")
    print("  - Hanya gunakan kartu magic milik sendiri.")
    print("  - Dump asli sebaiknya sudah dicadangkan.")
    print()
    if not args.yes:
        if not sys.stdin.isatty():
            raise CardError(
                "Mode non-interaktif: tambahkan --yes untuk benar-benar menulis."
            )
        answer = input("Ketik YA untuk melanjutkan: ").strip().upper()
        if answer not in {"YA", "Y"}:
            print("Dibatalkan.")
            return 1

    keys = resolve_existing(args.keys) if args.keys else None
    with ProxmarkClient(**_client_kwargs(args)) as client:
        info = client.search()
        print(
            f"Target: UID {info.uid_hex}"
            + (f", SAK {info.sak}" if info.sak else "")
            + (f", ATQA {info.atqa}" if info.atqa else "")
            + (f", magic: {info.magic}" if info.magic else "")
        )
        warning = _magic_warning(args.backend, info.magic)
        if warning:
            print(f"PERINGATAN: {warning}")
        print()

        if not args.no_backup:
            backup_card, _ = client.read_card(keys=keys, timeout=args.timeout)
            backup_dir = Path(args.backup_dir).expanduser()
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{backup_card.uid_hex}_{stamp}.bin"
            backup_card.save(backup_path)
            backup_card.save_json(backup_path.with_suffix(".json"))
            print(f"Backup kartu: {backup_path.resolve()}")
        else:
            print("Backup kartu dilewati (--no-backup).")
        print()

        output = client.write_card(
            source,
            backend=args.backend,
            timeout=args.timeout,
        )
        tail = "\n".join(output.splitlines()[-15:])
        if tail:
            print(tail)
        print()

        if args.verify:
            result = client.verify_card(source, keys=keys, timeout=args.timeout)
            print(result.summary())
            if not result.ok:
                for block, expected, actual in result.diff_blocks:
                    print(
                        f"  blok {block:2d}: harap {expected.hex().upper()} "
                        f"baca {actual.hex().upper()}"
                    )
                return 2
        else:
            print("Verifikasi dilewati (--no-verify).")
    return 0


def cmd_ports(args: argparse.Namespace) -> int:
    ports = list_serial_ports()
    print("Port serial terdeteksi:")
    if not ports:
        print("  (tidak ada)")
    for item in ports:
        device = str(item.get("DeviceID", "")).strip()
        name = str(item.get("Name", "")).strip()
        pnp = str(item.get("PNPDeviceID", "")).strip()
        print(f"  {device:<8} {name}")
        if pnp:
            print(f"           {pnp}")
    print()
    print(f"Port yang akan dipakai Proxmark3: {find_port(args.port)}")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    if args.list:
        print(format_replay_table())
        return 0

    replay_set = get_replay_set(args.set)
    if getattr(args, "mode", 0):
        replay_set = replace(replay_set, mode=args.mode)
    if args.json:
        print(json.dumps(replay_set.summary(), indent=2, ensure_ascii=False))
        return 0

    print(f"Set              : {replay_set.name} ({replay_set.firmware_set})")
    print(f"UID              : {replay_set.uid}")
    print(f"File 0004        : {len(replay_set.file0004)} byte")
    print(f"File 0003        : {len(replay_set.file0003)} byte")
    print(f"Secure 0006/0007 : {len(replay_set.secure)} byte")
    print(f"Challenge 0006   : {replay_set.challenge_0006.hex().upper()}")
    print(f"Challenge 0007   : {replay_set.challenge_0007.hex().upper()}")
    print()
    print("Perintah Proxmark3:")
    print(f"  {replay_set.simaid_command()}")
    print()
    print("Firmware harus memakai set yang sama:")
    print(f"  py proxmark_patch\\build_flash.py --set {replay_set.firmware_set} --flash")
    print(f"  py printer_test.py --set {replay_set.name} --seconds 600")
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    ok, _ = run_selftest(args.dir, verbose=True)
    return 0 if ok else 1


def cmd_gui(args: argparse.Namespace) -> int:
    from .gui import main as gui_main

    gui_main()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gtink",
        description=(
            "GTInk - analisis, clone, dan tulis chip kartrid EAJet/GT1000 "
            "(MIFARE Classic 1K) serta replay emulator ISO14443-4."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Contoh:\n"
            "  py gtink.py info --detail\n"
            "  py gtink.py analyze\n"
            "  py gtink.py clone --recommended --out clones\n"
            "  py gtink.py write --file clones/1EB75C2C_full_65000.bin "
            "--backend gen1a --port COM11 --yes\n"
            "  py gtink.py replay --set C\n"
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_dump_dir(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--dir",
            default=str(DEFAULT_DUMP_DIR),
            help=f"folder dump (default: {DEFAULT_DUMP_DIR})",
        )

    info = sub.add_parser("info", help="tabel dan rincian dump")
    info.add_argument("paths", nargs="*", help="file dump tertentu")
    add_dump_dir(info)
    info.add_argument("--detail", action="store_true", help="rincian tiap kartu")
    info.add_argument("--json", action="store_true", help="keluaran JSON")
    info.set_defaults(func=cmd_info)

    analyze_p = sub.add_parser("analyze", help="analisis lengkap keempat dump")
    add_dump_dir(analyze_p)
    analyze_p.add_argument("--output", help="simpan laporan ke file")
    analyze_p.set_defaults(func=cmd_analyze)

    clone = sub.add_parser("clone", help="buat file clone dan script Proxmark3")
    clone.add_argument("--source", help="file dump sumber")
    clone.add_argument("--source-uid", help="pilih dump berdasarkan UID")
    add_dump_dir(clone)
    clone.add_argument("--counter", type=_parse_int, help="counter 0..65535")
    clone.add_argument(
        "--fill",
        choices=("keep", "00", "ff"),
        default="keep",
        help="pola fill tail: keep/00/ff (default: keep)",
    )
    clone.add_argument("--fill-byte", type=_parse_int, help="fill 0..255")
    clone.add_argument("--new-uid", type=_parse_uid, help="UID baru 4 byte")
    clone.add_argument(
        "--random-uid",
        action="store_true",
        help="UID baru deterministik dari payload",
    )
    clone.add_argument("--label", help="label nama file")
    clone.add_argument("--tail-from", help="ambil tail dari dump lain")
    clone.add_argument("--no-sync", action="store_true", help="jangan samakan record 1/2")
    clone.add_argument("--recommended", action="store_true", help="paket rekomendasi")
    clone.add_argument("--out", default="clones", help="folder output")
    clone.add_argument(
        "--backend",
        action="append",
        choices=("gen1a", "gen2", "gen4"),
        help="backend script (boleh berulang)",
    )
    clone.set_defaults(func=cmd_clone)

    scripts = sub.add_parser("scripts", help="buat script dari file BIN yang sudah ada")
    scripts.add_argument("--file", required=True, help="file BIN clone")
    scripts.add_argument("--out", default="scripts", help="folder output")
    scripts.add_argument("--stem", help="nama dasar file script")
    scripts.add_argument(
        "--backend",
        action="append",
        choices=("gen1a", "gen2", "gen4"),
        help="backend script (boleh berulang)",
    )
    scripts.set_defaults(func=cmd_scripts)

    read = sub.add_parser("read", help="baca kartu lewat Proxmark3")
    read.add_argument("--out", default="readback.bin", help="file hasil")
    read.add_argument("--port", help="port serial, mis. COM11")
    read.add_argument("--client", help="path proxmark3.exe")
    read.add_argument("--keys", help="file key 192 byte")
    read.add_argument("--timeout", type=int, default=240, help="timeout detik")
    read.set_defaults(func=cmd_read)

    write = sub.add_parser("write", help="tulis clone ke kartu magic")
    write.add_argument("--file", required=True, help="file BIN clone")
    write.add_argument(
        "--backend",
        default="gen1a",
        choices=("gen1a", "gen2", "gen4"),
        help="jenis kartu magic (default: gen1a)",
    )
    write.add_argument("--port", help="port serial, mis. COM11")
    write.add_argument("--client", help="path proxmark3.exe")
    write.add_argument("--keys", help="file key 192 byte")
    write.add_argument("--timeout", type=int, default=240, help="timeout detik")
    write.add_argument("--yes", action="store_true", help="tanpa konfirmasi")
    write.add_argument("--no-verify", dest="verify", action="store_false", help="lewati verifikasi")
    write.add_argument("--no-backup", action="store_true", help="lewati backup")
    write.add_argument("--backup-dir", default="backups", help="folder backup")
    write.add_argument(
        "--allow-invalid",
        action="store_true",
        help="tetap tulis walau validasi clone error",
    )
    write.set_defaults(func=cmd_write, verify=True)

    ports = sub.add_parser("ports", help="daftar port serial")
    ports.add_argument("--port", help="tampilkan port tertentu")
    ports.set_defaults(func=cmd_ports)

    selftest = sub.add_parser("selftest", help="uji offline seluruh logika")
    add_dump_dir(selftest)
    selftest.set_defaults(func=cmd_selftest)

    replay = sub.add_parser(
        "replay",
        help="perintah emulator ISO14443-4 (Proxmark3 simaid)",
    )
    replay.add_argument(
        "--set",
        choices=sorted(REPLAY_SETS),
        default="C",
        help="state kartu yang diputar ulang (default C)",
    )
    replay.add_argument(
        "--mode",
        type=int,
        choices=(0, 1, 2, 3),
        default=0,
        help="mode tulis emulator: 0=abaikan asing, 1=simpan file0004 asing, "
             "2=simpan semua, 3=tolak asing",
    )
    replay.add_argument("--list", action="store_true", help="daftar state replay")
    replay.add_argument("--json", action="store_true", help="keluaran JSON")
    replay.set_defaults(func=cmd_replay)

    gui = sub.add_parser("gui", help="buka antarmuka Tkinter")
    gui.set_defaults(func=cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (CardError, ProxmarkError, FileNotFoundError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nDibatalkan.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
