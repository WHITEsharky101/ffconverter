"""streams_data.json serialization (CWD-relative, as before).

The config wizard saves {"streams": [AudioSubStream…], "params": FFmpegParam}
as UTF-8 JSON. Plain dataclass fields only — no pickle, no legacy formats.
"""
import json
from dataclasses import asdict

from ffcore.models import AudioSubStream, FFmpegParam

SAVE_FILE = "streams_data.json"


def save_data(data, path=SAVE_FILE):
    payload = {
        "streams": [asdict(s) for s in data["streams"]],
        "params": asdict(data["params"]),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_config(path=SAVE_FILE):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    streams = [AudioSubStream(**s) for s in data["streams"]]
    params = FFmpegParam(**data["params"])
    return streams, params
