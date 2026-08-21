"""Unit tests for process_string() robustness (ffmpeg_converter.py).

2026-08-21 fix: invalid episode-range input must never crash — invalid
tokens are skipped with a warning and valid tokens are still returned.

Run:  python3 -m unittest tests.test_process_string -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ffmpeg_converter import process_string


class ProcessStringValid(unittest.TestCase):
    """Valid inputs must stay byte-identical to pre-fix behavior."""

    def test_range(self):
        self.assertEqual(process_string("1-3"), ["01", "02", "03"])

    def test_single(self):
        self.assertEqual(process_string("7"), ["07"])

    def test_mixed(self):
        self.assertEqual(process_string("1 4-5"), ["01", "04", "05"])

    def test_spaces_around_range(self):
        self.assertEqual(process_string("2 - 4"), ["02", "03", "04"])

    def test_dash_only(self):
        self.assertEqual(process_string("-"), [])


class ProcessStringInvalid(unittest.TestCase):
    """Invalid inputs: no exception, valid remainder kept, all-invalid -> []."""

    def test_multi_hyphen_token_skipped(self):
        self.assertEqual(process_string("1-2-3"), [])

    def test_non_numeric_skipped(self):
        self.assertEqual(process_string("abc"), [])

    def test_valid_remainder_kept(self):
        self.assertEqual(process_string("1 abc 3"), ["01", "03"])

    def test_dangling_hyphen_skipped(self):
        self.assertEqual(process_string("5-"), [])

    def test_reversed_range_skipped(self):
        self.assertEqual(process_string("5-1"), [])

    def test_huge_range_skipped(self):
        # 100000 > MAX_RANGE_SPAN (10000): must be skipped, not materialized
        self.assertEqual(process_string("1-100000"), [])


class ProcessStringNoRaise(unittest.TestCase):
    """Regression: none of the crash inputs may raise any exception."""

    def test_no_exception_on_any_invalid(self):
        for s in ("1-2-3", "1--5", "abc", "5-", "-5", "5-1",
                 "1-100000", "", "  "):
            with self.subTest(inp=s):
                process_string(s)


if __name__ == "__main__":
    unittest.main()
