from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gtink.analysis import load_dump_dir
from gtink.card import Card
from gtink.clone import (
    CloneSpec,
    format_results,
    make_clone,
    recommended_specs,
    write_clone_result,
    write_recommended,
)


class CloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.cards = load_dump_dir()
        except FileNotFoundError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.primary = next(
            (card for card in cls.cards if card.uid_hex == "1EB75C2C"),
            cls.cards[0],
        )

    def test_recommended_specs(self) -> None:
        specs = recommended_specs(self.cards)
        self.assertGreaterEqual(len(specs), 9)
        labels = [spec.label for spec in specs]
        self.assertTrue(any("exact" in label for label in labels))
        self.assertTrue(any("full_65000" in label for label in labels))
        self.assertTrue(any("max_65535" in label for label in labels))
        self.assertTrue(any("newuid" in label for label in labels))
        new_uid_spec = next(spec for spec in specs if "newuid" in spec.label)
        self.assertIsNotNone(new_uid_spec.uid)
        self.assertNotIn(
            new_uid_spec.uid.hex().upper(),
            {card.uid_hex for card in self.cards},
        )
        low_specs = [spec for spec in specs if spec.source.counter <= 30000]
        self.assertTrue(any(spec.fill == 0xFF for spec in low_specs))
        self.assertTrue(any(spec.fill is None for spec in low_specs))

    def test_single_clone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_clone_result(
                CloneSpec(self.primary, 65000, "test_65000"),
                tmp,
                script_backends=("gen1a", "gen2", "gen4"),
            )
            self.assertTrue(result.bin_path.exists())
            self.assertTrue(result.json_path.exists())
            loaded = Card.from_file(result.bin_path)
            self.assertEqual(loaded.counters, (65000, 65000))
            self.assertFalse(loaded.has_errors())
            self.assertEqual(
                set(loaded.diff_bytes(self.primary)),
                {29 * 16 + 10, 29 * 16 + 11, 58 * 16 + 10, 58 * 16 + 11},
            )
            self.assertEqual(len(result.scripts), 3)

    def test_write_recommended_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = write_recommended(
                self.cards, tmp, script_backends=("gen1a", "gen2", "gen4")
            )
            folder = Path(tmp)
            self.assertTrue((folder / "manifest.json").exists())
            self.assertTrue((folder / "README_UJI.txt").exists())
            manifest = json.loads(
                (folder / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(manifest["clones"]), len(results))
            self.assertEqual(len(results), len(recommended_specs(self.cards)))
            for result in results:
                self.assertTrue(result.bin_path.exists())
                self.assertTrue(result.json_path.exists())
                self.assertTrue(all(path.exists() for path in result.scripts.values()))
                self.assertEqual(
                    Card.from_file(result.bin_path).counters,
                    (result.spec.counter, result.spec.counter),
                )
            exact = next(
                result
                for result in results
                if result.spec.source.uid == self.primary.uid
                and result.spec.counter == self.primary.counter
                and result.spec.uid is None
                and result.spec.fill is None
            )
            self.assertEqual(bytes(exact.card.data), bytes(self.primary.data))

    def test_format_results(self) -> None:
        clone = make_clone(CloneSpec(self.primary, 65000, "format"))
        with tempfile.TemporaryDirectory() as tmp:
            result = write_clone_result(
                CloneSpec(self.primary, 65000, "format"),
                tmp,
                script_backends=("gen1a",),
            )
            text = format_results([result])
        self.assertIn("format", text)
        self.assertIn(self.primary.uid_hex, text)
        self.assertIn("65000", text)
        self.assertEqual(clone.counters, (65000, 65000))


if __name__ == "__main__":
    unittest.main()
