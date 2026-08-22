import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import create_ffmpeg_config as cfg
from create_ffmpeg_config import AudioSubStream


def make_hevc_mkv(path):
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "testsrc=duration=0.2:size=64x64:rate=10",
        "-c:v", "libx265", "-preset", "ultrafast", path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 0, "ffmpeg failed: " + result.stderr.decode()[:500]


def mkstream(path="", codec=""):
    return AudioSubStream(
        stream=0, index=0, type="a", path=path, fonts=[],
        lang="jpn", title="Original", codec=codec,
    )


class TestHasFlacAudio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_embedded_flac_stream(self):
        self.assertTrue(cfg.has_flac_audio(self.tmp, [mkstream("", "flac")]))

    def test_embedded_flac_case_insensitive(self):
        self.assertTrue(cfg.has_flac_audio(self.tmp, [mkstream("", "FLAC")]))

    def test_no_flac_embedded_or_external(self):
        ext_dir = os.path.join(self.tmp, "audio")
        os.makedirs(ext_dir)
        with open(os.path.join(ext_dir, "track.mp3"), "wb") as f:
            f.write(b"fake")
        self.assertFalse(cfg.has_flac_audio(self.tmp, [mkstream("", "aac"), mkstream("audio", "")]))

    def test_external_flac_file(self):
        ext_dir = os.path.join(self.tmp, "audio")
        os.makedirs(ext_dir)
        with open(os.path.join(ext_dir, "track.flac"), "wb") as f:
            f.write(b"fake")
        self.assertTrue(cfg.has_flac_audio(self.tmp, [mkstream("audio", "")]))

    def test_no_streams(self):
        self.assertFalse(cfg.has_flac_audio(self.tmp, []))


class TestGetVideoCodec(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.video_dir = os.path.join(self.tmp, "video")
        os.makedirs(self.video_dir)
        make_hevc_mkv(os.path.join(self.video_dir, "episode.mkv"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_hevc(self):
        self.assertEqual(cfg.get_video_codec(self.video_dir), "hevc")

    def test_missing_directory(self):
        self.assertEqual(cfg.get_video_codec(os.path.join(self.tmp, "nope")), "")

    def test_no_media_files(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        self.assertEqual(cfg.get_video_codec(empty), "")


class TestMainIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # base_path / media_folder so folder_to_probe = tmp/S01
        self.s01 = os.path.join(self.tmp, "S01")
        os.makedirs(self.s01)
        make_hevc_mkv(os.path.join(self.s01, "episode.mkv"))
        self.saved = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_main(self, audio_raw, subtitle_raw, stdin_lines):
        out = io.StringIO()
        with mock.patch.object(cfg, "prompt_user_for_media",
                               return_value=(self.tmp, "S01", [], "TestMedia", "01")), \
             mock.patch.object(cfg, "ffprobe_media",
                               return_value=(audio_raw, subtitle_raw)), \
             mock.patch.object(cfg, "collect_additional_streams",
                               return_value=([], [])), \
             mock.patch.object(cfg, "change_mapping",
                               side_effect=lambda a, s, t: a + s), \
             mock.patch.object(cfg, "save_data",
                               side_effect=lambda d: self.saved.append(d)), \
             mock.patch("builtins.input", side_effect=stdin_lines), \
             mock.patch("sys.stdout", out):
            cfg.main()
        return out.getvalue()

    def test_flac_present_yes(self):
        raw = [{"index": 0, "codec_name": "flac",
                "tags": {"language": "jpn", "title": "Original"}}]
        out = self.run_main(raw, [], ["", "", "", "y"])
        self.assertIn("Текущий видеокодек: hevc", out)
        # the 4th input was consumed by the flac question -> True
        self.assertTrue(self.saved[0]["params"].flac_convert)

    def test_flac_present_no(self):
        raw = [{"index": 0, "codec_name": "flac",
                "tags": {"language": "jpn", "title": "Original"}}]
        out = self.run_main(raw, [], ["", "", "", "n"])
        self.assertIn("Текущий видеокодек: hevc", out)
        self.assertFalse(self.saved[0]["params"].flac_convert)

    def test_no_flac_skipped(self):
        raw = [{"index": 0, "codec_name": "aac",
                "tags": {"language": "jpn", "title": "Original"}}]
        # only 3 inputs: if the flac question is still asked, input() raises
        out = self.run_main(raw, [], ["", "", ""])
        self.assertIn("Текущий видеокодек: hevc", out)
        self.assertIn("FLAC-дорожек не найдено", out)
        self.assertFalse(self.saved[0]["params"].flac_convert)


if __name__ == "__main__":
    unittest.main()
