from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gtink.analysis import discover_dumps
from gtink.card import (
    BLOCK_COUNT,
    CARD_SIZE,
    COUNTER_BLOCKS,
    COUNTER_OFFSET,
    KNOWN_COUNTERS,
    Card,
    CardError,
)
from gtink.clone import CloneSpec, make_clone


class CardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        paths = discover_dumps()
        if len(paths) < 4:
            raise unittest.SkipTest("dump sumber tidak lengkap")
        cls.cards = [Card.from_file(path) for path in paths]
        cls.primary = next(
            (card for card in cls.cards if card.uid_hex == "1EB75C2C"),
            cls.cards[0],
        )
        cls.low = next(
            (card for card in cls.cards if card.counter <= 30000),
            cls.cards[-1],
        )

    def test_all_dumps_load(self) -> None:
        self.assertGreaterEqual(len(self.cards), 4)
        for card in self.cards:
            self.assertEqual(len(card.data), CARD_SIZE)
            self.assertEqual(len(list(card.blocks())), BLOCK_COUNT)

    def test_known_counters(self) -> None:
        for card in self.cards:
            self.assertEqual(card.counter, KNOWN_COUNTERS[card.uid_hex])
            self.assertEqual(card.counters[0], card.counters[1])
            self.assertTrue(card.counter_synced)

    def test_structure(self) -> None:
        for card in self.cards:
            self.assertTrue(card.bcc_ok)
            self.assertTrue(card.payloads_equal)
            self.assertTrue(card.tails_equal_without_counter)
            self.assertFalse(card.has_errors())
            self.assertEqual(len(card.record_data_blocks(4)), 22)
            self.assertEqual(len(card.record_payload_blocks(4)), 12)
            self.assertEqual(len(card.record_tail_blocks(4)), 10)
            self.assertFalse(
                any(Card.is_trailer(block) for block in card.record_data_blocks(4))
            )

    def test_exact_clone(self) -> None:
        for card in self.cards:
            clone = make_clone(CloneSpec(card, card.counter, "exact"))
            self.assertEqual(bytes(clone.data), bytes(card.data))

    def test_counter_edit_only_counter_bytes(self) -> None:
        clone = make_clone(CloneSpec(self.primary, 65000, "counter"))
        expected = {
            block * 16 + COUNTER_OFFSET + offset
            for block in COUNTER_BLOCKS
            for offset in (0, 1)
        }
        self.assertEqual(set(clone.diff_bytes(self.primary)), expected)
        self.assertEqual(clone.counters, (65000, 65000))
        self.assertFalse(clone.has_errors())

    def test_uid_edit_updates_bcc(self) -> None:
        new_uid = bytes.fromhex("A1B2C3D4")
        clone = make_clone(CloneSpec(self.primary, self.primary.counter, "uid", uid=new_uid))
        self.assertEqual(clone.uid, new_uid)
        self.assertTrue(clone.bcc_ok)
        self.assertEqual(set(clone.diff_bytes(self.primary)), set(range(5)))

    def test_low_fill_normalization(self) -> None:
        clone = make_clone(CloneSpec(self.low, 65000, "lowfill", fill=0xFF))
        self.assertEqual(clone.payload, self.low.payload)
        self.assertEqual(clone.counters, (65000, 65000))
        self.assertEqual(clone.counter_fill, 0xFF)
        for block in COUNTER_BLOCKS:
            self.assertEqual(clone.counter_header(block), b"\xff" * 10)
        for block in (30, 32, 60, 62):
            self.assertEqual(clone.block(block), b"\x00" * 16)
        self.assertFalse(clone.has_errors())

    def test_json_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "card.json"
            self.primary.save_json(path)
            loaded = Card.from_file(path)
            self.assertEqual(bytes(loaded.data), bytes(self.primary.data))

    def test_eml_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "card.eml"
            self.primary.save_eml(path)
            loaded = Card.from_file(path)
            self.assertEqual(bytes(loaded.data), bytes(self.primary.data))

    def test_validation_detects_bad_bcc(self) -> None:
        broken = self.primary.copy()
        broken.data[4] ^= 0xFF
        self.assertFalse(broken.bcc_ok)
        self.assertTrue(broken.has_errors())

    def test_bad_size(self) -> None:
        with self.assertRaises(CardError):
            Card(b"\x00" * 100)

    def test_counter_range(self) -> None:
        card = self.primary.copy()
        with self.assertRaises(ValueError):
            card.set_counter(65536)
        with self.assertRaises(ValueError):
            card.set_counter(-1)
        card.set_counter(0)
        self.assertEqual(card.counters, (0, 0))


if __name__ == "__main__":
    unittest.main()
