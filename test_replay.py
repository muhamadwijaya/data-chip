from __future__ import annotations

import contextlib
import io
import unittest

from gtink.cli import main
from gtink.replay import SETS, format_table, get_set


class ReplayDataTests(unittest.TestCase):
    def test_all_sets_present(self) -> None:
        self.assertEqual(
            set(SETS),
            {"A", "B", "C", "factory", "E", "S1", "S2", "S3", "S4"},
        )

    def test_lengths(self) -> None:
        for name, replay_set in SETS.items():
            with self.subTest(set=name):
                self.assertEqual(len(replay_set.file0004), 188)
                self.assertEqual(len(replay_set.file0003), 32)
                self.assertEqual(len(replay_set.secure), 88)
                self.assertEqual(len(replay_set.challenge_0006), 4)
                self.assertEqual(len(replay_set.challenge_0007), 4)
                self.assertEqual(len(replay_set.selectaid_response), 220)

    def test_challenge_mapping(self) -> None:
        expected = {
            "A": ("691d4fc3", "1a6ace1f"),
            "B": ("96bf9a55", "877e5087"),
            "C": ("b9be715f", "a61d5a69"),
            "factory": ("b9be715f", "a61d5a69"),
            "E": ("5ce27f48", "41a9aefb"),
            "S1": ("6896080f", "9f8df552"),
            "S2": ("7de780ea", "9f6399f2"),
            "S3": ("73cf4916", "951d1c8c"),
            "S4": ("a31d4870", "1550d1f1"),
        }
        for name, (ch6, ch7) in expected.items():
            with self.subTest(set=name):
                self.assertEqual(SETS[name].challenge_0006.hex(), ch6)
                self.assertEqual(SETS[name].challenge_0007.hex(), ch7)

    def test_factory_uses_set_c_secure_data(self) -> None:
        self.assertEqual(SETS["factory"].secure, SETS["C"].secure)

    def test_set_e_matches_real_d5(self) -> None:
        replay_set = SETS["E"]
        self.assertEqual(replay_set.file0004[-2:].hex(), "6726")
        self.assertEqual(
            replay_set.file0003.hex(),
            "33333430343430381800323033303236323038343539313720202020757df505",
        )
        self.assertEqual(
            replay_set.secure[0:40].hex(),
            "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f12a3509a3da2d48a8f9f40824dda44a86818",
        )
        self.assertEqual(replay_set.secure[40:44].hex(), "cda9f666")
        self.assertEqual(
            replay_set.secure[44:84].hex(),
            "3368d89983278d9f75f0e5d3b70f83877b01ed14f70f12a3509a3da2d48a8f9f40824dda44a86818",
        )
        self.assertEqual(replay_set.secure[84:88].hex(), "f6706da0")

    def test_real_d5_chain_order(self) -> None:
        chain = ["S1", "S2", "S3", "S4", "E"]
        tails = ["e726", "6f26", "d726", "6e26", "6726"]
        for name, tail in zip(chain, tails):
            with self.subTest(set=name):
                self.assertEqual(SETS[name].file0004[-2:].hex(), tail)
        # Setiap state punya response MAC berbeda untuk file 0006/0007.
        macs = {
            name: (SETS[name].secure[40:44].hex(), SETS[name].secure[84:88].hex())
            for name in chain
        }
        self.assertEqual(len(set(macs.values())), len(chain))

    def test_simaid_command_contains_payloads(self) -> None:
        replay_set = SETS["C"]
        cmd = replay_set.simaid_command()
        self.assertIn("hf 14a simaid", cmd)
        self.assertIn(replay_set.uid, cmd)
        self.assertIn(replay_set.selectaid_response.hex(), cmd)
        self.assertIn(replay_set.secure.hex(), cmd)
        self.assertIn(replay_set.ats, cmd)
        self.assertIn(replay_set.aid, cmd)

    def test_get_set_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            get_set("Z")

    def test_format_table(self) -> None:
        table = format_table()
        for name in SETS:
            self.assertIn(name, table)


class ReplayCliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(argv)
        return code, output.getvalue()

    def test_replay_list(self) -> None:
        code, output = self.run_cli(["replay", "--list"])
        self.assertEqual(code, 0)
        self.assertIn("factory", output)
        self.assertIn("Firmware", output)

    def test_replay_set_c(self) -> None:
        code, output = self.run_cli(["replay", "--set", "C"])
        self.assertEqual(code, 0)
        self.assertIn("Challenge 0006", output)
        self.assertIn("B9BE715F", output)
        self.assertIn("hf 14a simaid", output)

    def test_replay_json(self) -> None:
        code, output = self.run_cli(["replay", "--set", "A", "--json"])
        self.assertEqual(code, 0)
        self.assertIn('"set": "A"', output)
        self.assertIn('"challenge_0006": "691d4fc3"', output)


if __name__ == "__main__":
    unittest.main()
