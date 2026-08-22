"""Unit tests for output filename construction (ffmpeg_converter.py).

2026-08-22 user rule: the bracket tag in the output filename carries the
codec only for hevc -> ' [HEVC]' and av1 -> ' [AV1]'; h264 and codec
copy must produce a bare name (the old code printed '[H264]' and, worse,
'[]' for copy).

Run: python3 -m unittest tests.test_output_filename -v
"""

import types
import unittest

import ffmpeg_converter


def make_params(codec, output_ext=".mkv", path="/media/Show/Show S01", season="01"):
    return types.SimpleNamespace(
        name="Show",
        season=season,
        path=path,
        codec=codec,
        output_ext=output_ext,
    )


class CodecTagTest(unittest.TestCase):
    def test_hevc(self):
        self.assertEqual(ffmpeg_converter.codec_tag("hevc"), "HEVC")

    def test_av1_legacy_option(self):
        # CODECS menu lists AV1 as "av1(Его нет)" — the tag must still work.
        self.assertEqual(ffmpeg_converter.codec_tag("av1(Его нет)"), "AV1")

    def test_h264_no_tag(self):
        self.assertEqual(ffmpeg_converter.codec_tag("h264"), "")

    def test_copy_empty_no_tag(self):
        self.assertEqual(ffmpeg_converter.codec_tag(""), "")


class GenerateOutputFilesTest(unittest.TestCase):
    def test_hevc_bracket_tag(self):
        p = make_params("hevc")
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_output_files(p, "01", False),
            "/media/Show/Show S01/Show S01E01 [HEVC].mkv",
        )

    def test_h264_no_brackets(self):
        p = make_params("h264")
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_output_files(p, "01", False),
            "/media/Show/Show S01/Show S01E01.mkv",
        )

    def test_copy_no_empty_brackets(self):
        """Old bug: copy produced 'Show S01E01 [].mkv'."""
        p = make_params("")
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_output_files(p, "01", False),
            "/media/Show/Show S01/Show S01E01.mkv",
        )

    def test_av1_bracket_tag(self):
        p = make_params("av1(Его нет)")
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_output_files(p, "01", False),
            "/media/Show/Show S01/Show S01E01 [AV1].mkv",
        )

    def test_special_episode_uses_s00(self):
        p = make_params("hevc")
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_output_files(p, "01", True),
            "/media/Show/Show S01/Show S00E01 [HEVC].mkv",
        )

    def test_tmp_path_strips_tmp_dirname(self):
        p = make_params("hevc", path="/media/Show/Show S01/.tmp")
        self.assertEqual(
            ffmpeg_converter.generate_ffmpeg_output_files(p, "01", False),
            "/media/Show/Show S01/Show S01E01 [HEVC].mkv",
        )


if __name__ == "__main__":
    unittest.main()
