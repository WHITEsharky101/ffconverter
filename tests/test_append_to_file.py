"""Unit tests for append_to_file() convertlist location (ffmpeg_converter.py).

2026-08-21 fix: convertlist.txt must be written next to the source
code (script directory) instead of the hardcoded /data/media/anime/
path. The target lives in the module constant CONVERTLIST_PATH; tests
patch it to a temp dir for isolation.

Run: python3 -m unittest tests.test_append_to_file -v
"""

import os
import tempfile
import unittest
from unittest import mock

import ffmpeg_converter


class TestConvertlistLocation(unittest.TestCase):
    def test_default_path_is_next_to_source(self):
        """CONVERTLIST_PATH resolves to convertlist.txt beside the script."""
        self.assertEqual(
            os.path.basename(ffmpeg_converter.CONVERTLIST_PATH),
            'convertlist.txt',
        )
        self.assertEqual(
            os.path.dirname(ffmpeg_converter.CONVERTLIST_PATH),
            os.path.dirname(os.path.abspath(ffmpeg_converter.__file__)),
        )


class TestAppendToFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = os.path.join(self._tmp.name, 'convertlist.txt')
        self._patcher = mock.patch.object(
            ffmpeg_converter, 'CONVERTLIST_PATH', self.target
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    def test_writes_line_with_newline(self):
        ffmpeg_converter.append_to_file('line1')
        with open(self.target, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'line1\n')

    def test_multiple_calls_append_in_order(self):
        ffmpeg_converter.append_to_file('first')
        ffmpeg_converter.append_to_file('second')
        with open(self.target, encoding='utf-8') as f:
            self.assertEqual(f.readlines(), ['first\n', 'second\n'])

    def test_missing_directory_does_not_raise(self):
        bad = os.path.join(self._tmp.name, 'no-such-dir', 'convertlist.txt')
        with mock.patch.object(ffmpeg_converter, 'CONVERTLIST_PATH', bad):
            ffmpeg_converter.append_to_file('x')  # must not raise

    def test_utf8_roundtrip(self):
        ffmpeg_converter.append_to_file('Русский текст 123')
        with open(self.target, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'Русский текст 123\n')


if __name__ == '__main__':
    unittest.main()
