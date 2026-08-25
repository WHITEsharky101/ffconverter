"""JSON storage contract for ffcore.storage (replaces the pickle tests).

The config artifact is now human-readable UTF-8 JSON in CWD
(streams_data.json). No pickle, no legacy __main__ class registration.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import create_ffmpeg_config as cfc
from ffcore import storage
from ffcore.models import AudioSubStream, FFmpegParam

STREAM_ATTRS = dict(
    stream=0, index=0, type="a",
    path="/media/series/Death Note/Death Note S01/Death Note S01E01.mka",
    fonts=[], lang="jpn", title="Original", codec="flac",
)
PARAM_ATTRS = dict(
    name="Death Note", season="S01",
    path="/media/series/Death Note/Death Note S01",
    episodes=["Death Note S01E01"], sp_episodes=[],
    video_ext="", audio_ext=[".mka"], sub_ext=[".ass"], output_ext=".mkv",
    flac_convert=False, codec="hevc", tune_preset="slow", cut_time=[],
)


def make_data(crf=None, bit=None):
    return {"streams": [AudioSubStream(**STREAM_ATTRS)],
            "params": FFmpegParam(**PARAM_ATTRS, crf=crf, bit=bit)}


class JsonStorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, name="streams_data.json"):
        return os.path.join(self.tmp, name)

    def test_roundtrip_new_format(self):
        p = self.path()
        storage.save_data(make_data(), p)
        # File on disk must be human-readable JSON, not pickle bytes.
        with open(p, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(sorted(on_disk), ["params", "streams"])
        streams, params = storage.load_config(p)
        self.assertIsInstance(streams[0], AudioSubStream)
        self.assertIsInstance(params, FFmpegParam)
        self.assertEqual(params.name, "Death Note")
        self.assertEqual(params.season, "S01")
        self.assertEqual(streams[0].title, "Original")
        self.assertIsNone(params.crf)
        self.assertIsNone(params.bit)

    def test_crf_roundtrip(self):
        p = self.path()
        storage.save_data(make_data(crf=18, bit=10), p)
        _, params = storage.load_config(p)
        self.assertEqual(params.crf, 18)
        self.assertEqual(params.bit, 10)

    def test_cyrillic_paths_readable(self):
        data = make_data()
        data["params"].name = "Сумма Технологий"
        data["params"].path = "/lib/Сумма/Сумма S01"
        p = self.path()
        storage.save_data(data, p)
        with open(p, encoding="utf-8") as f:
            raw = f.read()
        self.assertIn("Сумма", raw)
        self.assertNotIn("\\u0421", raw)  # no \uXXXX escapes
        streams, params = storage.load_config(p)
        self.assertEqual(params.name, "Сумма Технологий")
        self.assertEqual(params.path, "/lib/Сумма/Сумма S01")

    def test_entry_reexports_match_ffcore(self):
        # The entry-point re-exports are what wizard/converter/tests rely on.
        self.assertIs(cfc.AudioSubStream, AudioSubStream)
        self.assertIs(cfc.FFmpegParam, FFmpegParam)
        self.assertIs(cfc.save_data, storage.save_data)
        self.assertEqual(cfc.SAVE_FILE, storage.SAVE_FILE)
        self.assertEqual(storage.SAVE_FILE, "streams_data.json")

    def test_converter_reuses_single_save_file(self):
        # ffmpeg_converter must import SAVE_FILE, not hardcode a second copy
        # (a rename in ffcore/storage.py would silently desync otherwise).
        import ffmpeg_converter
        self.assertIs(ffmpeg_converter.SAVE_FILE, storage.SAVE_FILE)

    def test_corrupt_file_raises_value_error(self):
        p = self.path("corrupt.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertRaises(ValueError, storage.load_config, p)

    def test_corrupt_file_reruns_wizard(self):
        # Corrupt CWD streams_data.json: load_data must not traceback —
        # it re-runs the wizard (which re-saves) and loads the fresh file.
        import ffmpeg_converter
        corrupt = os.path.join(self.tmp, "streams_data.json")
        with open(corrupt, "w", encoding="utf-8") as f:
            f.write("{not json")
        wizard_calls = []

        def fake_main():
            wizard_calls.append(1)
            storage.save_data(make_data())  # wizard re-saves the artifact

        old_cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            with mock.patch.object(cfc, "main", side_effect=fake_main), \
                    mock.patch("builtins.input", return_value="y"):
                streams, params = ffmpeg_converter.load_data()
        finally:
            os.chdir(old_cwd)
        self.assertEqual(len(wizard_calls), 1)
        self.assertEqual(params.name, "Death Note")
        self.assertIsInstance(streams[0], AudioSubStream)


if __name__ == "__main__":
    unittest.main()
