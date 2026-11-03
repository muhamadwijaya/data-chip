from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from .card import (
    BLOCK_COUNT,
    DEFAULT_KEY,
    Card,
)


DEFAULT_CLIENT_CANDIDATES = (
    Path(r"C:\ProxSpace\pm3\proxmark3\client\proxmark3.exe"),
    Path(r"C:\ProxSpace\pm3\proxmark3\client\proxmark3"),
    Path.home() / "ProxSpace" / "pm3" / "proxmark3" / "client" / "proxmark3.exe",
    Path.home() / "ProxSpace" / "pm3" / "proxmark3" / "client" / "proxmark3",
)

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class ProxmarkError(RuntimeError):
    """Kesalahan saat menjalankan Proxmark3 client."""


@dataclass
class ProxmarkInfo:
    uid: bytes
    uid_hex: str
    sak: str | None = None
    atqa: str | None = None
    magic: str | None = None
    raw: str = ""


@dataclass
class VerifyResult:
    ok: bool
    expected: Card
    actual: Card | None
    diff_blocks: list[tuple[int, bytes, bytes]] = field(default_factory=list)
    output: str = ""

    def summary(self) -> str:
        if self.ok:
            return f"Verifikasi OK: {self.expected.uid_hex}, {BLOCK_COUNT} blok sama."
        if self.actual is None:
            return "Verifikasi GAGAL: kartu tidak bisa dibaca kembali."
        if self.diff_blocks:
            blocks = ", ".join(str(block) for block, _, _ in self.diff_blocks)
            return f"Verifikasi GAGAL: {len(self.diff_blocks)} blok berbeda ({blocks})."
        return "Verifikasi GAGAL."


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def _first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        try:
            if path.exists() and path.is_file():
                return path
        except OSError:
            continue
    return None


def find_client(explicit: str | Path | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path
        raise ProxmarkError(f"Proxmark3 client tidak ditemukan: {path}")

    env_path = os.environ.get("PROXMARK3_CLIENT")
    if env_path:
        path = Path(env_path).expanduser()
        if path.is_file():
            return path

    path = _first_existing(DEFAULT_CLIENT_CANDIDATES)
    if path is not None:
        return path

    which = shutil.which("proxmark3")
    if which:
        return Path(which)

    # Pencarian terbatas di ProxSpace, tanpa memindai seluruh drive.
    for root in (Path(r"C:\ProxSpace"), Path.home() / "ProxSpace"):
        if root.exists():
            matches = list(root.glob("**/client/proxmark3.exe"))
            matches += list(root.glob("**/client/proxmark3"))
            path = _first_existing(matches)
            if path is not None:
                return path

    raise ProxmarkError(
        "Proxmark3 client tidak ditemukan. Pasang ProxSpace/client Proxmark3, "
        "atau berikan path dengan --client / variabel PROXMARK3_CLIENT."
    )


def _windows_serial_ports() -> list[dict]:
    if os.name != "nt":
        return []
    command = (
        "Get-CimInstance Win32_SerialPort | "
        "Select-Object DeviceID,Name,PNPDeviceID | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    text = (result.stdout or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def list_serial_ports() -> list[dict]:
    """Daftar port serial yang terlihat oleh OS."""
    if os.name == "nt":
        return _windows_serial_ports()

    ports: list[dict] = []
    for pattern in (
        "/dev/ttyACM*",
        "/dev/ttyUSB*",
        "/dev/cu.usbmodem*",
        "/dev/cu.usbserial*",
    ):
        for path in sorted(Path("/").glob(pattern.lstrip("/"))):
            ports.append(
                {
                    "DeviceID": str(path),
                    "Name": str(path),
                    "PNPDeviceID": "",
                }
            )
    return ports


def find_port(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env_port = os.environ.get("PROXMARK3_PORT")
    if env_port:
        return env_port

    if os.name == "nt":
        ports = _windows_serial_ports()
        for item in ports:
            pnp = str(item.get("PNPDeviceID", "")).upper()
            if "VID_9AC4" in pnp or "PROXMARK" in pnp or "ICEMAN" in pnp:
                device = str(item.get("DeviceID", "")).strip()
                if device:
                    return device
        names = [str(item.get("DeviceID", "")).strip() for item in ports]
        if "COM11" in names:
            return "COM11"
        for name in names:
            if name.upper().startswith("COM"):
                return name
        return "COM11"

    for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*"):
        matches = sorted(Path("/").glob(pattern.lstrip("/")))
        if matches:
            return str(matches[0])
    return "/dev/ttyACM0"


def _path_for_client(path: str | Path) -> str:
    value = str(Path(path).resolve()).replace("\\", "/")
    if " " in value or "\t" in value:
        return f'"{value}"'
    return value


def _path_for_script(path: str | Path) -> str:
    return _path_for_client(path)


class ProxmarkClient:
    def __init__(
        self,
        client: str | Path | None = None,
        port: str | None = None,
        workdir: str | Path | None = None,
        timeout: int = 180,
    ) -> None:
        self.client = find_client(client)
        self.port = find_port(port)
        self.timeout = timeout
        self._owns_workdir = workdir is None
        self.workdir = Path(
            workdir
            if workdir is not None
            else tempfile.mkdtemp(prefix="gtink_pm3_")
        )
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.env = self._build_env()

    def close(self) -> None:
        if self._owns_workdir:
            shutil.rmtree(self.workdir, ignore_errors=True)

    def __enter__(self) -> "ProxmarkClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        extra_paths: list[str] = []
        for parent in self.client.parents:
            msys_bin = parent / "msys2" / "mingw64" / "bin"
            if msys_bin.is_dir():
                extra_paths.append(str(msys_bin))
                break
        extra_paths.append(str(self.client.parent))
        if extra_paths:
            env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])
        # Qt plugin tidak dibutuhkan untuk mode CLI, tetapi aman bila ada.
        for parent in self.client.parents:
            plugin = parent / "libs"
            if plugin.is_dir():
                env.setdefault("QT_PLUGIN_PATH", str(plugin))
                env.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(plugin))
                break
        return env

    def _run(
        self,
        command: str,
        timeout: int | None = None,
        cwd: str | Path | None = None,
        allow_failure: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            str(self.client),
            "--incognito",
            "-p",
            self.port,
            "-c",
            command,
        ]
        try:
            result = subprocess.run(
                args,
                cwd=str(cwd or self.workdir),
                env=self.env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProxmarkError(f"Tidak bisa menjalankan client: {self.client}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProxmarkError(
                f"Perintah Proxmark3 timeout setelah {timeout or self.timeout} detik: {command}"
            ) from exc

        output = strip_ansi((result.stdout or "") + (result.stderr or ""))
        if result.returncode != 0 and not allow_failure:
            tail = "\n".join(output.splitlines()[-25:])
            if "invalid serial port" in output.lower():
                tail += (
                    "\nHint: port serial mungkin sedang dipakai aplikasi lain "
                    "(client Proxmark3 lain), kabel terputus, atau nama port berubah. "
                    "Tutup aplikasi tersebut lalu cek dengan: py gtink.py ports"
                )
            raise ProxmarkError(
                f"Perintah Proxmark3 gagal (exit {result.returncode}): {command}\n{tail}"
            )
        result.stdout = output
        result.stderr = ""
        return result

    def version(self) -> str:
        return self._run("hw version", timeout=60).stdout

    def search(self) -> ProxmarkInfo:
        output = self._run("hf search", timeout=90).stdout
        uid_match = re.search(
            r"UID:\s*((?:[0-9A-Fa-f]{2}\s*){4})", output
        )
        if not uid_match:
            raise ProxmarkError(
                "Tidak ada kartu ISO14443-A yang terdeteksi. "
                "Letakkan kartu di atas antena Proxmark3."
            )
        uid = bytes.fromhex(re.sub(r"\s+", "", uid_match.group(1)))
        sak_match = re.search(r"SAK:\s*([0-9A-Fa-f]{2})", output)
        atqa_match = re.search(
            r"ATQA:\s*((?:[0-9A-Fa-f]{2}\s*){2})", output
        )
        magic_match = re.search(
            r"Magic capabilities\.\.\.\s*(.+)", output
        )
        return ProxmarkInfo(
            uid=uid,
            uid_hex=uid.hex().upper(),
            sak=sak_match.group(1).upper() if sak_match else None,
            atqa=re.sub(r"\s+", "", atqa_match.group(1)).upper()
            if atqa_match
            else None,
            magic=magic_match.group(1).strip() if magic_match else None,
            raw=output,
        )

    @staticmethod
    def _key_file_bytes() -> bytes:
        # 16 sektor x (Key A 6 byte + Key B 6 byte) = 192 byte.
        return DEFAULT_KEY * (16 * 2)

    def read_card(
        self,
        keys: str | Path | None = None,
        timeout: int | None = None,
    ) -> tuple[Card, str]:
        info = self.search()
        read_dir = self.workdir / f"read_{info.uid_hex}"
        read_dir.mkdir(parents=True, exist_ok=True)
        key_name = f"hf-mf-{info.uid_hex}-key.bin"
        key_path = read_dir / key_name
        if keys is not None:
            key_data = Path(keys).read_bytes()
            if len(key_data) != 192:
                raise ProxmarkError(
                    f"Key file harus 192 byte, bukan {len(key_data)} byte: {keys}"
                )
            key_path.write_bytes(key_data)
        else:
            key_path.write_bytes(self._key_file_bytes())

        base = "readback"
        command = f"hf mf dump -f {base} --1k -k {key_name}"
        result = self._run(
            command,
            timeout=timeout or 180,
            cwd=read_dir,
        )
        bin_path = read_dir / f"{base}.bin"
        if not bin_path.exists():
            json_path = read_dir / f"{base}.json"
            if json_path.exists():
                return Card.from_file(json_path), result.stdout
            raise ProxmarkError(
                "Dump selesai tetapi file readback.bin tidak ditemukan.\n"
                + "\n".join(result.stdout.splitlines()[-20:])
            )
        return Card.from_file(bin_path), result.stdout

    def write_card(
        self,
        clone_path: str | Path,
        backend: str = "gen1a",
        timeout: int | None = None,
    ) -> str:
        source = Path(clone_path)
        if not source.is_file():
            raise ProxmarkError(f"File clone tidak ditemukan: {source}")
        card = Card.from_file(source)
        backend = backend.lower()

        if backend in {"gen1a", "gen1", "1a"}:
            target = self.workdir / "clone.bin"
            shutil.copy2(source, target)
            result = self._run(
                f"hf mf cload -f clone.bin --1k",
                timeout=timeout or 240,
            )
            return result.stdout

        if backend in {"gen4", "g4", "gtu"}:
            target = self.workdir / "clone.bin"
            shutil.copy2(source, target)
            result = self._run(
                f"hf mf gload -f clone.bin --1k",
                timeout=timeout or 240,
            )
            return result.stdout

        if backend in {"gen2", "gen2uid", "cuid", "gen1b"}:
            commands: list[str] = []
            # Blok 0 ditulis terakhir: mengubah UID di tengah proses bisa
            # membuat kartu perlu dipilih ulang dan mengganggu blok berikutnya.
            order = list(range(1, BLOCK_COUNT)) + [0]
            for index in order:
                data = card.block(index).hex().upper()
                command = (
                    f"hf mf wrbl --blk {index} -k FFFFFFFFFFFF -d {data}"
                )
                if index == 0:
                    command += " --force"
                commands.append(command)
            # Satu string -c; output tiap perintah tetap ditampilkan oleh client.
            result = self._run(
                "; ".join(commands),
                timeout=timeout or 360,
            )
            return result.stdout

        raise ProxmarkError(
            f"Backend tidak dikenal: {backend} (pakai gen1a, gen2, atau gen4)"
        )

    def verify_card(
        self,
        expected_path: str | Path,
        keys: str | Path | None = None,
        timeout: int | None = None,
    ) -> VerifyResult:
        expected = Card.from_file(expected_path)
        actual, output = self.read_card(keys=keys, timeout=timeout)
        diff = expected.diff_blocks(actual)
        return VerifyResult(
            ok=not diff,
            expected=expected,
            actual=actual,
            diff_blocks=diff,
            output=output,
        )

    def write_and_verify(
        self,
        clone_path: str | Path,
        backend: str = "gen1a",
        keys: str | Path | None = None,
        timeout: int | None = None,
    ) -> VerifyResult:
        self.write_card(clone_path, backend=backend, timeout=timeout)
        return self.verify_card(clone_path, keys=keys, timeout=timeout)


def generate_scripts(
    bin_path: str | Path,
    script_dir: str | Path,
    backend: str,
    stem: str,
    card: Card | None = None,
) -> Path:
    """Buat script perintah Proxmark3 untuk backend tertentu."""
    source = Path(bin_path)
    output = Path(script_dir)
    output.mkdir(parents=True, exist_ok=True)
    backend = backend.lower()
    path_text = _path_for_script(source)

    if backend in {"gen1a", "gen1", "1a"}:
        lines = [
            "hf mf cload -f " + path_text + " --1k",
        ]
        suffix = "gen1a"
    elif backend in {"gen4", "g4", "gtu"}:
        lines = [
            "hf mf gload -f " + path_text + " --1k",
        ]
        suffix = "gen4"
    elif backend in {"gen2", "gen2uid", "cuid", "gen1b"}:
        if card is None:
            card = Card.from_file(source)
        lines = []
        order = list(range(1, BLOCK_COUNT)) + [0]
        for index in order:
            data = card.block(index).hex().upper()
            command = f"hf mf wrbl --blk {index} -k FFFFFFFFFFFF -d {data}"
            if index == 0:
                command += " --force"
            lines.append(command)
        suffix = "gen2"
    else:
        raise ProxmarkError(f"Backend tidak dikenal: {backend}")

    path = output / f"{stem}_{suffix}.txt"
    header = [
        "# Script Proxmark3 - GTInk",
        f"# Backend: {suffix}",
        f"# Clone : {source.name}",
        "# Jalankan dari client Proxmark3, contoh:",
        f"#   proxmark3 -p COM11 -s \"{path.name}\"",
        "",
    ]
    path.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
    return path


def readme_commands(clone_path: str | Path, backend: str = "gen1a") -> str:
    path_text = _path_for_client(clone_path)
    if backend == "gen1a":
        return f'hf mf cload -f {path_text} --1k'
    if backend == "gen4":
        return f'hf mf gload -f {path_text} --1k'
    if backend == "gen2":
        return "Gunakan script gen2 (satu perintah hf mf wrbl per blok)."
    return f"Backend tidak dikenal: {backend}"
