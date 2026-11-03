from __future__ import annotations

import unittest

from gtink.selftest import run_selftest


class SelftestTests(unittest.TestCase):
    def test_selftest_passes(self) -> None:
        ok, checks = run_selftest(verbose=False)
        self.assertTrue(ok)
        self.assertGreaterEqual(len(checks), 10)
        self.assertTrue(all(item[0] for item in checks))


if __name__ == "__main__":
    unittest.main()
