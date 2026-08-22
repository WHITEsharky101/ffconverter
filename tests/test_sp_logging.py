"""Unit tests for the convertlist episode log line (ffmpeg_converter.py).

2026-08-22 fix: special episodes (S00) were never written to
convertlist.txt — the append_to_file call existed only in the normal
episode loop. The line format is now a shared pure helper
episode_log_line(params, season, episode, formatted_time) used by both
the sp loop (season '00') and the normal loop (params.season).

Run: python3 -m unittest tests.test_sp_logging -v
"""

import types
import unittest

import ffmpeg_converter


def make_params(crf=18, season="01"):
    return types.SimpleNamespace(name="Show", season=season, crf=crf)


class EpisodeLogLineTest(unittest.TestCase):
    def test_normal_episode_matches_legacy_format(self):
        """Byte-identical to the old inline f-string."""
        p = make_params()
        self.assertEqual(
            ffmpeg_converter.episode_log_line(p, p.season, "01", "00:01:29"),
            "Show S01E01 [18][00:01:29]",
        )

    def test_special_episode_uses_s00(self):
        p = make_params()
        self.assertEqual(
            ffmpeg_converter.episode_log_line(p, "00", "01", "00:02:00"),
            "Show S00E01 [18][00:02:00]",
        )

    def test_error_time_marker(self):
        p = make_params()
        self.assertEqual(
            ffmpeg_converter.episode_log_line(p, p.season, "05", "ERROR!!!"),
            "Show S01E05 [18][ERROR!!!]",
        )

    def test_copy_mode_none_crf(self):
        p = make_params(crf=None)
        self.assertEqual(
            ffmpeg_converter.episode_log_line(p, p.season, "01", "00:00:10"),
            "Show S01E01 [None][00:00:10]",
        )


if __name__ == "__main__":
    unittest.main()
