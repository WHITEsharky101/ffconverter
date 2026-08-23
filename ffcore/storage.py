"""streams_data.pkl serialization (CWD-relative, as before)."""
import os
import pickle
import sys

SAVE_FILE = "streams_data.pkl"


def _register_legacy_classes():
    """Pre-refactor pickles record classes under ``__main__``.

    Register the real ffcore.models classes there so such pickles
    resolve on load (same trick the smoke recipe used by hand).
    """
    main = sys.modules.get("__main__")
    if main is None:
        return
    from ffcore.models import AudioSubStream, FFmpegParam
    for name, cls in (("AudioSubStream", AudioSubStream),
                      ("FFmpegParam", FFmpegParam)):
        setattr(main, name, cls)


def save_data(data, path=SAVE_FILE):
    with open(path, "wb") as f:
        pickle.dump(data, f)


def load_config(path=SAVE_FILE):
    _register_legacy_classes()
    with open(path, "rb") as f:
        data = pickle.load(f)
    return data["streams"], data["params"]
