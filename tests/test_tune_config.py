"""Unit tests for generate_ffmpeg_tune_config() in ffmpeg_converter.py.

2026-08-22 fix: when the tune preset question is skipped (empty input ->
tune=""), the generated command contained a dangling '-tune' whose value
position was eaten by '-crf 18' after the empty-arg filter, producing
`-tune -crf 18` -> ffmpeg: "Error opening output file 18". The -tune
argument must be omitted entirely when tune is empty.

Run: python3 -m unittest tests.test_tune_config -v
"""

import unittest

import ffmpeg_converter


class GenerateFfmpegTuneConfigTest(unittest.TestCase):
    def test_crf_without_tune_has_no_tune_flag(self):
        """Skipping the preset (tune='') must not emit a dangling -tune."""
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_tune_config(18, ""),
            ["-crf", "18"],
        )

    def test_crf_with_tune(self):
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_tune_config(18, "animation"),
            ["-tune", "animation", "-crf", "18"],
        )

    def test_no_crf_copy_mode(self):
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_tune_config(None, "animation"),
            [],
        )

    def test_no_crf_no_tune(self):
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_tune_config(None, ""),
            [],
        )


if __name__ == "__main__":
    unittest.main()
