"""Data model shared by the config wizard and the converter.

Field order in FFmpegParam keeps the legacy positional slots
(name, season, path, episodes, sp_episodes, video_ext, audio_ext,
sub_ext, output_ext, flac_convert, codec, bit, tune_preset, cut_time);
`crf` is appended last — the converter finalizes it in collect_inputs.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AudioSubStream:
    """One audio or subtitle stream (embedded: path=='' / external: path)."""
    stream: int
    index: int
    type: str          # "a" | "s"
    path: str
    fonts: List[str] = field(default_factory=list)
    lang: str = ""
    title: Optional[str] = None
    codec: str = ""


@dataclass
class FFmpegParam:
    """Conversion parameters for one season of one media title."""
    name: str
    season: str
    path: str
    episodes: List[str] = field(default_factory=list)
    sp_episodes: List[str] = field(default_factory=list)
    video_ext: str = ""
    audio_ext: list = field(default_factory=list)
    sub_ext: list = field(default_factory=list)
    output_ext: str = ""
    flac_convert: bool = False
    codec: str = ""
    bit: Optional[int] = None
    tune_preset: str = ""
    cut_time: list = field(default_factory=list)
    crf: Optional[int] = None
