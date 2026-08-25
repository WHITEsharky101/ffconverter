"""Unit tests for aq-mode/row-mt placement in generate_ffmpeg_command (ffcore/ffmpeg.py).

2026-08-24 fix: '-aq-mode 3' and '-row-mt 1' were passed as TOP-LEVEL ffmpeg
arguments. ffmpeg silently ignores them ("Codec AVOption aq-mode (adaptive
quantization mode) has not been used for any stream"), so x265 never
received aq-mode=3 — anime encodes ran without AQ (banding, washed-out
dark scenes). x265 private options belong in '-x265-params' (the same
dictionary that already carries asm=avx512). For non-hevc codecs
(h264 / copy) there is no x265 consumer, so the flag is dropped entirely.

Run: python3 -m unittest tests.test_aq_mode -v
"""
import os
import tempfile
import types
import unittest

from ffcore import ffmpeg as ff


def make_params(tmp, codec="hevc", crf=18, tune="animation"):
    media_dir = os.path.join(tmp, "Show S01")
    os.makedirs(media_dir, exist_ok=True)
    open(os.path.join(media_dir, "Show S01E01.mp4"), "w").close()
    return types.SimpleNamespace(
        name="Show",
        season="01",
        path=media_dir,
        video_ext=[".mp4"],
        audio_ext=[],
        sub_ext=[],
        flac_convert=False,
        output_ext=".mp4",
        codec=codec,
        bit=8,
        crf=crf,
        tune_preset=tune,
        cut_time=[],
    )


class AqModePlacementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.params = make_params(self.tmp.name)

    def command(self):
        return ff.generate_ffmpeg_command([], self.params, "01", False)

    def test_aq_mode_lives_in_x265_params(self):
        cmd = self.command()
        i = cmd.index("-x265-params")
        self.assertEqual(cmd[i + 1], "asm=avx512:aq-mode=3:row-mt=1")

    def test_no_top_level_aq_mode(self):
        self.assertNotIn("-aq-mode", self.command())

    def test_no_top_level_row_mt(self):
        self.assertNotIn("-row-mt", self.command())

    def test_hevc_keeps_existing_flags(self):
        """-preset slow / -threads 0 stay in place around the fix."""
        cmd = self.command()
        self.assertEqual(cmd[cmd.index("-preset") + 1], "slow")
        self.assertEqual(cmd[cmd.index("-threads") + 1], "0")

    def test_h264_has_no_x265_params(self):
        self.params.codec = "h264"
        cmd = self.command()
        self.assertNotIn("-x265-params", cmd)
        self.assertNotIn("-aq-mode", cmd)

    def test_copy_mode_has_no_x265_params(self):
        self.params.codec = None
        self.params.crf = None
        cmd = self.command()
        self.assertNotIn("-x265-params", cmd)
        self.assertNotIn("-aq-mode", cmd)

    def test_cut_time_list_is_spread_into_argv(self):
        # format_timings returns an argv LIST; it must be unpacked into the
        # command, not appear as one nested element.
        self.params.cut_time = ["-ss", "00:00:10", "-to", "00:01:30"]
        cmd = self.command()
        i = cmd.index("-ss")
        self.assertEqual(cmd[i:i + 4], ["-ss", "00:00:10", "-to", "00:01:30"])

    def test_format_timings_returns_argv_list(self):
        from ffcore.text import format_timings
        self.assertEqual(
            format_timings("10 1:30"),
            ["-ss", "00:00:10", "-to", "00:01:30"])
        self.assertEqual(format_timings("garbage"), [])


if __name__ == "__main__":
    unittest.main()
