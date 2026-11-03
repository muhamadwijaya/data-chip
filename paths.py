from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


def resolve_existing(value: str | Path) -> Path:
    """Kembalikan path yang ada; coba relatif terhadap root proyek.

    Saat program dijalankan lewat shortcut atau dari folder lain, path relatif
    seperti ``tij gt1000 CHIP INK`` tetap ditemukan.
    """
    path = Path(value).expanduser()
    if path.is_absolute() or path.exists():
        return path
    alternative = PROJECT_ROOT / path
    if alternative.exists():
        return alternative
    return path


def default_dump_dir() -> Path:
    return resolve_existing("tij gt1000 CHIP INK")


def default_output_dir() -> Path:
    return Path("clones")
