from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gtink.analysis import load_dump_dir
from gtink.proxmark import (
    ProxmarkClient,
    find_client,
    find_port,
    generate_scripts,
    list_serial_ports,
    strip_ansi,
)


class ProxmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.cards = load_dump_dir()
        except FileNotFoundError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.primary = cls.cards[0]

    def test_strip_ansi(self) -> None:
        self.assertEqual(strip_ansi("\x1b[31mmerah\x1b[0m"), "merah")

    def test_key_file_size(self) -> None:
        self.assertEqual(len(ProxmarkClient._key_file_bytes()), 192)

    def test_generate_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            bin_path = folder / "sample.bin"
            self.primary.save(bin_path)
            scripts = {
                backend: generate_scripts(
                    bin_path, folder, backend, "sample", self.primary
                )
                for backend in ("gen1a", "gen2", "gen4")
            }
            for path in scripts.values():
                self.assertTrue(path.exists())
                text = path.read_text(encoding="utf-8")
                self.assertIn("Script Proxmark3", text)

            def commands(path: Path) -> list[str]:
                return [
                    line.strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]

            gen1a = commands(scripts["gen1a"])
            self.assertEqual(len(gen1a), 1)
            self.assertTrue(gen1a[0].startswith("hf mf cload"))
            self.assertIn("--1k", gen1a[0])

            gen2 = commands(scripts["gen2"])
            self.assertEqual(len(gen2), 64)
            self.assertTrue(gen2[0].startswith("hf mf wrbl --blk 1"))
            self.assertTrue(gen2[-1].startswith("hf mf wrbl --blk 0"))
            self.assertIn("--force", gen2[-1])

            gen4 = commands(scripts["gen4"])
            self.assertEqual(len(gen4), 1)
            self.assertTrue(gen4[0].startswith("hf mf gload"))
            self.assertIn("--1k", gen4[0])

    def test_explicit_port(self) -> None:
        self.assertEqual(find_port("COM99"), "COM99")

    def test_list_serial_ports(self) -> None:
        ports = list_serial_ports()
        self.assertIsInstance(ports, list)

    def test_find_client_if_installed(self) -> None:
        path = Path(r"C:\ProxSpace\pm3\proxmark3\client\proxmark3.exe")
        if not path.exists():
            self.skipTest("Proxmark3 client tidak terpasang")
        self.assertEqual(find_client().resolve(), path.resolve())


if __name__ == "__main__":
    unittest.main()
