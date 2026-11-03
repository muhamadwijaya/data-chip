from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from gtink.analysis import load_dump_dir
from gtink.cli import main


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.cards = load_dump_dir()
        except FileNotFoundError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.primary = cls.cards[0]

    def run_cli(self, argv: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(argv)
        return code, output.getvalue()

    def test_info(self) -> None:
        code, output = self.run_cli(["info"])
        self.assertEqual(code, 0)
        for card in self.cards:
            self.assertIn(card.uid_hex, output)

    def test_info_json(self) -> None:
        code, output = self.run_cli(["info", "--json"])
        self.assertEqual(code, 0)
        self.assertIn('"uid"', output)

    def test_analyze(self) -> None:
        code, output = self.run_cli(["analyze"])
        self.assertEqual(code, 0)
        self.assertIn("Kandidat counter", output)

    def test_selftest(self) -> None:
        code, output = self.run_cli(["selftest"])
        self.assertEqual(code, 0)
        self.assertIn("SELFTEST LULUS", output)

    def test_clone_single(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self.run_cli(
                [
                    "clone",
                    "--source",
                    str(self.primary.source),
                    "--counter",
                    "65000",
                    "--out",
                    tmp,
                    "--backend",
                    "gen1a",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("65000", output)
            files = list(Path(tmp).glob("*.bin"))
            self.assertEqual(len(files), 1)
            self.assertTrue((Path(tmp) / "scripts").is_dir())

    def test_clone_recommended(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self.run_cli(
                ["clone", "--recommended", "--out", tmp, "--backend", "gen1a"]
            )
            self.assertEqual(code, 0)
            self.assertIn("manifest.json", output)
            self.assertTrue((Path(tmp) / "manifest.json").exists())

    def test_scripts_from_bin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bin_path = Path(tmp) / "sample.bin"
            self.primary.save(bin_path)
            out = Path(tmp) / "scripts"
            code, output = self.run_cli(
                ["scripts", "--file", str(bin_path), "--out", str(out)]
            )
            self.assertEqual(code, 0)
            self.assertTrue((out / "sample_gen1a.txt").exists())
            self.assertIn("sample_gen1a.txt", output)
            self.assertIn(
                "cload",
                (out / "sample_gen1a.txt").read_text(encoding="utf-8"),
            )

    def test_bad_counter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self.run_cli(
                [
                    "clone",
                    "--source",
                    str(self.primary.source),
                    "--counter",
                    "70000",
                    "--out",
                    tmp,
                ]
            )
            self.assertNotEqual(code, 0)
            self.assertIn("ERROR", output)


if __name__ == "__main__":
    unittest.main()
