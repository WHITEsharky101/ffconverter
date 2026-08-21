"""Unit tests for the media-file lookup helpers in create_ffmpeg_config.

Covers the crash fixes for:
- media_getter(): UnboundLocalError when no file matches,
  FileNotFoundError when the folder is missing
- ffprobe_media(): inconsistent 3-tuple return on the no-media branch
- get_media_ext(): splitext on a missing file and loss of list parallelism

Run from the repo root:
    python3 -m unittest tests.test_media_getter -v
"""

import os
import sys
import tempfile
import unittest

# Make the project root importable regardless of the current working directory.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import create_ffmpeg_config as cfg


def _make_stream(index, stype, path):
    """Build an AudioSubStream with only the fields under test populated."""
    return cfg.AudioSubStream(
        stream=0,
        index=index,
        type=stype,
        path=path,
        fonts=[],
        lang="???",
        title=None,
        codec="",
    )


class MediaGetterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def test_empty_dir_returns_empty_string(self):
        self.assertEqual(cfg.media_getter(self.tmp, (".mkv",)), "")

    def test_no_match_returns_empty_string(self):
        with open(os.path.join(self.tmp, "notes.txt"), "w") as f:
            f.write("no media here")
        self.assertEqual(cfg.media_getter(self.tmp, (".mkv", ".mp4")), "")

    def test_missing_dir_returns_empty_string(self):
        self.assertEqual(
            cfg.media_getter(os.path.join(self.tmp, "does-not-exist"), (".mkv",)), ""
        )

    def test_match_returns_filename(self):
        with open(os.path.join(self.tmp, "episode.mkv"), "wb") as f:
            f.write(b"\x00" * 16)
        self.assertEqual(
            cfg.media_getter(self.tmp, (".mkv", ".mp4")), "episode.mkv"
        )


class FFprobeMediaTest(unittest.TestCase):
    def test_no_media_returns_empty_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Must return exactly a 2-tuple: main() unpacks two values.
            self.assertEqual(cfg.ffprobe_media(tmp), ([], []))


class GetMediaExtTest(unittest.TestCase):
    def _streams(self):
        return [
            _make_stream(0, "a", ""),      # embedded audio: no external path, skipped
            _make_stream(1, "a", "audio"), # external audio in ./audio
            _make_stream(2, "s", "subs"),  # external subs in ./subs
        ]

    def test_missing_files_return_parallel_empty_exts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "notes.txt"), "w") as f:
                f.write("no media here")
            video_ext, audio_ext, sub_ext = cfg.get_media_ext(
                tmp, self._streams()
            )
        self.assertEqual(video_ext, "")
        # One entry per external stream, even when the file is missing —
        # the converter indexes these lists positionally.
        self.assertEqual(audio_ext, [""])
        self.assertEqual(sub_ext, [""])

    def test_found_files_return_real_exts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "ep.mkv"), "wb") as f:
                f.write(b"\x00" * 16)
            os.makedirs(os.path.join(tmp, "audio"))
            os.makedirs(os.path.join(tmp, "subs"))
            with open(os.path.join(tmp, "audio", "ep.flac"), "wb") as f:
                f.write(b"\x00" * 16)
            with open(os.path.join(tmp, "subs", "ep.ass"), "w") as f:
                f.write("[Script Info]\n")
            video_ext, audio_ext, sub_ext = cfg.get_media_ext(
                tmp, self._streams()
            )
        self.assertEqual(video_ext, ".mkv")
        self.assertEqual(audio_ext, [".flac"])
        self.assertEqual(sub_ext, [".ass"])


if __name__ == "__main__":
    unittest.main()
