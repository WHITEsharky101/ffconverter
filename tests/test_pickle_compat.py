"""Pickle round-trip + legacy __main__-format compatibility (ffcore.storage).

Pre-refactor pickles were written by the scripts run as __main__, so they
record the model classes as __main__.AudioSubStream / __main__.FFmpegParam.
ffcore.storage.load_config must keep loading them: it registers the real
ffcore.models classes under sys.modules['__main__'] before unpickling.

Run: python3 -m unittest tests.test_pickle_compat -v
"""
import os
import pickle
import sys
import tempfile
import types
import unittest
from unittest import mock

import create_ffmpeg_config as cfc
from ffcore import storage
from ffcore.models import AudioSubStream, FFmpegParam


STREAM_ATTRS = dict(stream=0, index=0, type="a", path="",
                    fonts=[], lang="rus", title="X", codec="")
PARAM_ATTRS = dict(name="Show", season="01", path="/m/Show/Show S01",
                   episodes=[], sp_episodes=[], video_ext=".mkv",
                   audio_ext=[], sub_ext=[], output_ext=".mkv",
                   flac_convert=False, codec="", bit=None,
                   tune_preset="", cut_time=[])


def make_data():
    return {"streams": [AudioSubStream(**STREAM_ATTRS)],
            "params": FFmpegParam(**PARAM_ATTRS)}


def _legacy_instance(class_name, attrs):
    """An instance recorded under the __main__ module, like old pickles."""
    namespace = {}
    exec(f"class {class_name}(object):\n    pass", namespace)
    cls = namespace[class_name]
    cls.__module__ = "__main__"
    instance = cls.__new__(cls)
    instance.__dict__.update(attrs)
    return instance


def _dump_legacy_pickle(path):
    """Write a pickle whose classes resolve only via sys.modules['__main__']."""
    main_module = sys.modules["__main__"]
    stream_cls = _legacy_instance("AudioSubStream", STREAM_ATTRS)
    params_cls = _legacy_instance("FFmpegParam", PARAM_ATTRS)
    # pickle.dump verifies the class is reachable as __main__.<name>, so the
    # stubs must be present while dumping (removed afterwards).
    saved = {name: getattr(main_module, name, None) for name in
             ("AudioSubStream", "FFmpegParam")}
    main_module.AudioSubStream = type(stream_cls)
    main_module.FFmpegParam = type(params_cls)
    try:
        with open(path, "wb") as f:
            pickle.dump({"streams": [stream_cls], "params": params_cls}, f)
    finally:
        for name, old in saved.items():
            if old is None:
                delattr(main_module, name)
            else:
                setattr(main_module, name, old)


class StorageTest(unittest.TestCase):
    def test_roundtrip_new_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "streams_data.pkl")
            storage.save_data(make_data(), p)
            streams, params = storage.load_config(p)
        self.assertIsInstance(streams[0], AudioSubStream)
        self.assertIsInstance(params, FFmpegParam)
        self.assertEqual(params.name, "Show")
        self.assertEqual(params.season, "01")
        self.assertEqual(streams[0].title, "X")

    def test_entry_reexports_match_ffcore(self):
        # The config entry must keep exposing the model classes (tests,
        # pickle identity, smoke recipe all rely on cfc.AudioSubStream).
        self.assertIs(cfc.AudioSubStream, AudioSubStream)
        self.assertIs(cfc.FFmpegParam, FFmpegParam)
        self.assertIs(cfc.save_data, storage.save_data)
        self.assertEqual(cfc.SAVE_FILE, storage.SAVE_FILE)

    def test_legacy_main_module_format_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "streams_data.pkl")
            _dump_legacy_pickle(p)
            streams, params = storage.load_config(p)
        self.assertIsInstance(streams[0], AudioSubStream)
        self.assertIsInstance(params, FFmpegParam)
        self.assertEqual(type(streams[0]).__module__, "ffcore.models")
        self.assertEqual(type(params).__module__, "ffcore.models")
        self.assertEqual(streams[0].title, "X")
        self.assertEqual(params.name, "Show")
        self.assertEqual(params.path, "/m/Show/Show S01")

    def test_register_legacy_classes_is_idempotent(self):
        main_module = sys.modules["__main__"]
        storage._register_legacy_classes()
        self.assertIs(main_module.AudioSubStream, AudioSubStream)
        self.assertIs(main_module.FFmpegParam, FFmpegParam)
        storage._register_legacy_classes()
        self.assertIs(main_module.AudioSubStream, AudioSubStream)


if __name__ == "__main__":
    unittest.main()
